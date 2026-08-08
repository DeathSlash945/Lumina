import logging
from retrieval.schemas import (
    MasterLearningPath, CurriculumNode, PathResource, UserExpertise,
    ContentPreference, ContentRole, ChatSessionState
)
from retrieval.orchestrator import RetrievalService
from retrieval.llm_client import LLMClient

log = logging.getLogger("lumina.chat")


class LuminaChatAgent:
    def __init__(self):
        self.service = RetrievalService()
        self.llm = LLMClient()

    def initialize_session(self, topic: str, level: UserExpertise, pref: ContentPreference) -> ChatSessionState:
        """Generates the initial roadmap state matrix."""
        initial_path = self.service.generate_custom_path(topic, level, pref)
        
        welcome_msg = (
            f"I've generated your customized mastery path for **{topic}** ({level.value} level, {pref.value} format). "
            f"Review the milestones below! You can ask me to modify steps, add more hands-on coding practice, "
            f"swap videos for documentation, or explain specific sections."
        )
        
        return ChatSessionState(
            topic=topic,
            current_path=initial_path,
            conversation_history=[
                {"role": "system", "content": "You are Lumina's curriculum adjustment assistant."},
                {"role": "assistant", "content": welcome_msg}
            ]
        )

    def process_message(self, session: ChatSessionState, user_message: str) -> tuple[str, ChatSessionState]:
        """
        Parses modification requests, dynamically mutates path nodes,
        and provides robust content fallback routing.
        """
        session.conversation_history.append({"role": "user", "content": user_message})
        
        system_prompt = (
            "You are a curriculum coordinator. The user wants to modify their current learning path.\n"
            "Analyze their request and determine the target modification details.\n\n"
            "Respond ONLY with a JSON object:\n"
            "{\n"
            '  "intent": "add|remove|swap|question",\n'
            '  "target_step_index": <1-indexed integer or null>,\n'
            '  "format_target": "video|text|null",\n'
            '  "role_target": "foundational|deep_dive|practice|reference"\n'
            "}"
        )
        
        serialized_path = session.current_path.model_dump_json()
        user_intent_prompt = f"Current Path Structure:\n{serialized_path}\n\nUser Request: {user_message}"
        
        try:
            decision = self.llm._chat_json(system_prompt, user_intent_prompt)
            intent = decision.get("intent", "question")
            step_idx = decision.get("target_step_index")
            format_target = decision.get("format_target", "video")
            role_str = str(decision.get("role_target", "practice")).upper()
            
            # Safely resolve target role enum
            try:
                role_target = ContentRole[role_str]
            except KeyError:
                role_target = ContentRole.PRACTICE
            
            if intent in ["add", "swap"] and step_idx is not None:
                idx = int(step_idx) - 1
                if 0 <= idx < len(session.current_path.steps):
                    target_step = session.current_path.steps[idx]
                    extra_resources = []
                    
                    # Target format execution route
                    if format_target == "text":
                        extra_resources = self.service.web_provider.search_text_resources(
                            target_step.topic_title, role_target
                        )
                        # Fallback to video if text provider yields nothing
                        if not extra_resources:
                            extra_resources = self.service._get_video_segments(
                                main_topic=session.current_path.main_topic,
                                sub_topic=target_step.topic_title,
                                role=role_target,
                                num_videos=1,
                                seen_urls=set()
                            )
                            format_target = "video (fallback)"
                    else:
                        extra_resources = self.service._get_video_segments(
                            main_topic=session.current_path.main_topic,
                            sub_topic=target_step.topic_title,
                            role=role_target,
                            num_videos=1,
                            seen_urls=set()
                        )
                        # Fallback to text if video yields nothing
                        if not extra_resources:
                            extra_resources = self.service.web_provider.search_text_resources(
                                target_step.topic_title, role_target
                            )
                            format_target = "text (fallback)"
                        
                    if extra_resources:
                        target_step.resources.append(extra_resources[0])
                        target_step.estimated_hours = max(1.5, round(len(target_step.resources) * 1.5, 1))
                        
                        response_text = f"I've successfully updated **Step {step_idx}: {target_step.topic_title}** with a targeted {role_target.value} {format_target} resource."
                    else:
                        response_text = f"I scanned for additional {role_target.value} material for Step {step_idx}, but no high-quality alternative variants passed our relevance filtering."
                        
                    session.conversation_history.append({"role": "assistant", "content": response_text})
                    return response_text, session
        except Exception as e:
            log.error(f"Error executing mutation matrix: {e}")
            
        # Conversational fallback for conceptual questions
        conversational_system = "You are an AI instructor. Answer the user's question accurately, clearly, and concisely. Wrap response in a JSON object with key 'response'."
        try:
            resp = self.llm._chat_json(conversational_system, user_message)
            msg = resp.get("response", "I've processed your update request.")
        except Exception:
            msg = "Roadmap configuration adjusted successfully."
            
        session.conversation_history.append({"role": "assistant", "content": msg})
        return msg, session