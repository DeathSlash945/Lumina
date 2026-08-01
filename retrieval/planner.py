import json
import logging
from retrieval.llm_client import LLMClient
from retrieval.schemas import UserExpertise, ContentPreference, ContentRole

log = logging.getLogger("lumina.planner")

class CurriculumPlanner:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def structural_breakdown(self, topic: str, level: UserExpertise) -> list[str]:
        """
        Determines whether a topic is an entire course structure or a specific leaf.
        Generates robust contextual labels to enforce accurate search queries.
        """
        system_prompt = (
            "You are an expert academic advisor. Evaluate if the topic provided by the user is a broad macro-topic "
            "(e.g., 'Data Structures') or a narrow micro-topic/leaf-concept (e.g., 'Heaps').\n\n"
            "If it is a broad macro-topic, break it down into a linear sequence of 3 to 5 core milestone sub-topics for mastery.\n"
            "If it is a specific micro-topic, return ONLY a list containing that single topic string.\n\n"
            "Crucial: Ensure the topic strings contain explicit domain context so search engines do not confuse ambiguous concepts "
            "(e.g., use 'Heaps Data Structure' instead of just 'Heaps' to avoid memory stack/heap confusion).\n\n"
            f"Tailor depth for an '{level.value}' level.\n"
            "Respond strictly with a JSON object: {\"sub_topics\": [\"...\"]}"
        )
        
        user_prompt = f"Topic to analyze: '{topic}'"
        
        try:
            response = self.llm._chat_json(system_prompt, user_prompt)
            topics = response.get("sub_topics", [f"{topic} Data Structure"])
            log.info(f"Planned curriculum sequence for '{topic}': {topics}")
            return topics
        except Exception as e:
            log.warning(f"Failed to cleanly separate topic tree, adding safe context fallback: {e}")
            return [f"{topic} Data Structure"]

    def compute_role_weights(self, level: UserExpertise, preference: ContentPreference) -> dict[ContentRole, float]:
        """Ensures complete pedagogical coverage across all required beginner tiers."""
        if level == UserExpertise.BEGINNER:
            return {
                ContentRole.FOUNDATIONAL: 0.40,
                ContentRole.PRACTICE: 0.40,      # Elevated to ensure practice code is searched
                ContentRole.REFERENCE: 0.20,     # For beginner mistakes / tips
                ContentRole.DEEP_DIVE: 0.00      # Kept at 0 for pure beginners
            }
        
        base_weights = {
            UserExpertise.INTERMEDIATE: {
                ContentRole.FOUNDATIONAL: 0.20,
                ContentRole.DEEP_DIVE: 0.35,
                ContentRole.PRACTICE: 0.35,
                ContentRole.REFERENCE: 0.10
            },
            UserExpertise.EXPERT: {
                ContentRole.FOUNDATIONAL: 0.00,
                ContentRole.DEEP_DIVE: 0.50,
                ContentRole.PRACTICE: 0.30,
                ContentRole.REFERENCE: 0.20
            }
        }[level]
        
        return base_weights