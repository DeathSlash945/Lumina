import logging
from typing import Any, Dict, List, Optional
from retrieval.llm_client import LLMClient
from retrieval.schemas import UserExpertise, ContentPreference, ContentRole
from retrieval.agents import CurriculumPlannerAgent, RelatedTopicsAgent

log = logging.getLogger("lumina.planner")


class CurriculumPlanner:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.planner_agent = CurriculumPlannerAgent(self.llm)
        self.related_topics_agent = RelatedTopicsAgent(self.llm)

    def structural_breakdown(
        self, topic: str, level: UserExpertise, critique_feedback: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.planner_agent.plan_structure(topic, level, critique_feedback)

    def compute_role_weights(
        self, level: UserExpertise, preference: ContentPreference = None
    ) -> Dict[ContentRole, float]:
        if level == UserExpertise.BEGINNER:
            return {
                ContentRole.FOUNDATIONAL: 0.40,
                ContentRole.PRACTICE: 0.40,
                ContentRole.REFERENCE: 0.20,
                ContentRole.DEEP_DIVE: 0.00,
            }

        base_weights = {
            UserExpertise.INTERMEDIATE: {
                ContentRole.FOUNDATIONAL: 0.20,
                ContentRole.DEEP_DIVE: 0.35,
                ContentRole.PRACTICE: 0.35,
                ContentRole.REFERENCE: 0.10,
            },
            UserExpertise.EXPERT: {
                ContentRole.FOUNDATIONAL: 0.00,
                ContentRole.DEEP_DIVE: 0.50,
                ContentRole.PRACTICE: 0.30,
                ContentRole.REFERENCE: 0.20,
            },
        }[level]
        return base_weights

    def generate_related_topics(self, topic: str, sub_topics: List[Any]) -> List[str]:
        sub_topic_dicts = [
            t if isinstance(t, dict) else {"title": str(t)} for t in sub_topics
        ]
        return self.related_topics_agent.generate_related_topics(topic, sub_topic_dicts)