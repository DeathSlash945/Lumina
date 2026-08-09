import json
import logging
from typing import Any, Dict, List
from retrieval.llm_client import LLMClient
from retrieval.schemas import UserExpertise, ContentPreference, ContentRole

log = logging.getLogger("lumina.planner")

class CurriculumPlanner:

  def __init__(self, llm_client: LLMClient):
    self.llm = llm_client

  def structural_breakdown(
      self, topic: str, level: UserExpertise
  ) -> List[Dict[str, Any]]:
    """Determines whether a topic is an entire course structure or a specific leaf.
    Generates robust contextual labels to enforce accurate search queries.
    """
    system_prompt = (
        "You are an expert advisor building structured learning paths for the"
        " given topic.\n\n"
        "CRITICAL STEP RULES:\n"
        "1. STEP TYPES: Assign each step one of these types:\n"
        "   - 'foundational': Core concepts, overview, theory\n"
        "   - 'deep_dive': In-depth mechanics, internals, deep analysis\n"
        "   - 'practice': Hands-on exercises, walkthroughs, tutorials\n"
        "   - 'reference': Specs, official docs, cheatsheets, reference\n\n"
        "2. VARIABLE RESOURCES & RATIONALE:\n"
        "   - Do NOT restrict every step to 1 video and 1 text link.\n"
        "   - Specify 'recommended_videos' (1 to 4) and 'recommended_texts' (1"
        " to 3) based on needs.\n"
        "   - Provide a brief 'resource_rationale' explaining WHY this resource"
        " allocation was chosen (e.g., 'This topic requires heavy practice, so"
        " 3 hands-on walkthroughs are included.').\n\n"
        "3. ACCURATE TIME ESTIMATION:\n"
        "   - Estimate 'estimated_minutes' realistically based on the depth"
        " and required practice time (e.g., 20m for a quick foundational step,"
        " 90-150m for a complex coding practice step).\n\n"
        f"Tailor depth strictly for an '{level.value}' level.\n\n"
        "Respond strictly with JSON matching this structure:\n"
        "{\n"
        '  "sub_topics": [\n'
        "    {\n"
        '      "title": "...",\n'
        '      "step_type": "foundational | deep_dive | practice |'
        ' reference",\n'
        '      "estimated_minutes": 45,\n'
        '      "resource_rationale": "...",\n'
        '      "recommended_videos": 3,\n'
        '      "recommended_texts": 1\n'
        "    }\n"
        "  ]\n"
        "}"
    )
    user_prompt = f"Topic to analyze: '{topic}'"

    # Consistent dictionary fallback matching the required schema
    fallback = [{
        "title": f"{topic} Fundamentals",
        "step_type": "foundational",
        "estimated_minutes": 45,
        "resource_rationale": "Fallback foundational module.",
        "recommended_videos": 1,
        "recommended_texts": 1,
    }]

    try:
      response = self.llm._chat_json(user_prompt, system_prompt)
      topics = response.get("sub_topics", fallback)
      log.info(f"Planned curriculum sequence for '{topic}': {topics}")
      return topics
    except Exception as e:
      log.warning(
          "Failed to cleanly separate topic tree, adding safe context fallback:"
          f" {e}"
      )
      return fallback

  def compute_role_weights(
      self, level: UserExpertise, preference: ContentPreference = None
  ) -> dict[ContentRole, float]:
    """Ensures complete pedagogical coverage across all required beginner tiers."""
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

  def generate_related_topics(self, topic: str, sub_topics: list) -> list[str]:
    """Suggests adjacent/follow-up topics a learner might explore next."""
    titles = [
        t.get("title", str(t)) if isinstance(t, dict) else str(t)
        for t in sub_topics
    ]

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
      response = self.llm._chat_json(user_prompt, system_prompt)
      related = response.get("related_topics", [])
      return [str(r) for r in related][:10]
    except Exception as e:
      log.warning(f"Failed to generate related topics for '{topic}': {e}")
      return []

    