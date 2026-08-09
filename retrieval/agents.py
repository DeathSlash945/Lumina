import logging
from typing import List, Dict, Any, Optional, Union
from retrieval.schemas import UserExpertise
from retrieval.llm_client import LLMClient

log = logging.getLogger("lumina.agents")


class CurriculumPlannerAgent:
    """Agent 1: Generates structured sub-topics using strict step rules and prerequisite ordering."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def plan_structure(
        self, topic: str, level: Union[UserExpertise, str], critique_feedback: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        level_str = getattr(level, "value", level)

        system_prompt = (
            "You are an expert advisor building structured learning paths for the given topic.\n\n"
            "CRITICAL STEP RULES:\n"
            "1. PREREQUISITE ORDERING: Order steps logically. Foundational concepts MUST precede advanced implementations.\n"
            "2. STEP TYPES: Assign each step one of these types:\n"
            "   - 'foundational': Core concepts, overview, theory\n"
            "   - 'deep_dive': In-depth mechanics, internals, deep analysis\n"
            "   - 'practice': Hands-on exercises, walkthroughs, tutorials\n"
            "   - 'reference': Specs, official docs, cheatsheets, reference\n\n"
            "3. VARIABLE RESOURCES & RATIONALE:\n"
            "   - Do NOT restrict every step to 1 video and 1 text link.\n"
            "   - Specify 'recommended_videos' (0 to 4) and 'recommended_texts' (0 to 3) based on needs.\n"
            "   - Provide a brief 'resource_rationale' explaining WHY this resource allocation was chosen "
            "(e.g., 'This topic requires heavy practice, so 3 hands-on walkthroughs are included.').\n\n"
            "4. ACCURATE TIME ESTIMATION:\n"
            "   - Estimate 'estimated_minutes' realistically based on depth and practice time "
            "(e.g., 20m for a quick foundational step, 90-150m for a complex coding practice step).\n\n"
            f"Tailor depth strictly for an '{level_str}' level.\n\n"
            "Respond strictly with JSON matching this structure:\n"
            "{\n"
            '  "sub_topics": [\n'
            "    {\n"
            '      "title": "...",\n'
            '      "step_type": "foundational | deep_dive | practice | reference",\n'
            '      "estimated_minutes": 45,\n'
            '      "resource_rationale": "...",\n'
            '      "recommended_videos": 3,\n'
            '      "recommended_texts": 1\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        user_prompt = f"Topic to analyze: '{topic}'"
        if critique_feedback:
            user_prompt += f"\n\nCRITIC REVISION FEEDBACK: {critique_feedback}\nModify the subtopics to fix these issues."

        fallback = [{
            "title": f"{topic} Fundamentals",
            "step_type": "foundational",
            "estimated_minutes": 45,
            "resource_rationale": "Fallback foundational module.",
            "recommended_videos": 1,
            "recommended_texts": 1,
        }]

        try:
            res = self.llm._chat_json(user_prompt, system_prompt)
            if isinstance(res, dict) and "sub_topics" in res and isinstance(res["sub_topics"], list):
                return res["sub_topics"]
        except Exception as e:
            log.warning(f"Planner Agent execution error for '{topic}': {e}")

        return fallback


class CurriculumCriticAgent:
    """Agent 2: Evaluates proposed paths for logical flow, prerequisite correctness, and scope."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def evaluate_path(
        self, topic: str, level: Union[UserExpertise, str], sub_topics: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        level_str = getattr(level, "value", level)

        system_prompt = (
            "You are an expert Curriculum Critic Agent. Validate the proposed curriculum structure.\n"
            "Verify:\n"
            "1. Out-of-order prerequisites (e.g., advanced topics before foundational basics).\n"
            "2. Skill level suitability (are advanced concepts placed in a beginner path?).\n"
            "3. Logical progression and topic completeness.\n\n"
            "Respond ONLY in valid JSON format:\n"
            "{\n"
            '  "is_valid": true|false,\n'
            '  "feedback": "Detailed reason if invalid, or approval message."\n'
            "}"
        )

        user_prompt = f"Main Topic: {topic}\nSkill Level: {level_str}\nProposed Steps:\n{sub_topics}"

        try:
            res = self.llm._chat_json(user_prompt, system_prompt)
            if isinstance(res, dict) and "is_valid" in res:
                return res
        except Exception as e:
            log.warning(f"Critic evaluation failed: {e}. Auto-approving path.")

        return {"is_valid": True, "feedback": "Auto-approved path."}


class RelatedTopicsAgent:
    """Agent 3: Suggests adjacent subjects and next steps after completing the curriculum."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate_related_topics(self, topic: str, sub_topics: List[Dict[str, Any]]) -> List[str]:
        titles = [t.get("title", str(t)) if isinstance(t, dict) else str(t) for t in sub_topics]

        system_prompt = (
            "You suggest follow-up learning topics. Given a main topic and the"
            " subtopics already covered in its learning path, suggest 5-9 DISTINCT"
            " related topics the learner could explore next, things that build on,"
            " branch from, or commonly pair with the main topic. Avoid repeating"
            ' the subtopics already listed.\n\nRespond strictly with JSON: {"related_topics":'
            ' ["...", "..."]}'
        )
        user_prompt = f"Main topic: '{topic}'\nAlready covered: {titles}"

        try:
            res = self.llm._chat_json(user_prompt, system_prompt)
            if isinstance(res, dict) and "related_topics" in res:
                return [str(r) for r in res["related_topics"]][:10]
        except Exception as e:
            log.warning(f"Failed to generate related topics for '{topic}': {e}")

        return [f"Advanced {topic}", f"{topic} Architecture", f"Practical {topic} Projects"]