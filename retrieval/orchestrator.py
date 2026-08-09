import logging
from typing import Dict, List, Set, Optional
from retrieval.schemas import (
    MasterLearningPath, CurriculumNode, PathResource, ResourceType,
    UserExpertise, ContentPreference, ContentRole, CompletionStatus
)
from retrieval.providers.ytdlp_provider import YtDlpSearchProvider, YtDlpTranscriptProvider
from retrieval.providers.web_provider import WebSearchProvider
from retrieval.providers.book_provider import MultiSourceBookProvider
from retrieval.vector_store import VectorStore
from retrieval.llm_client import LLMClient
from retrieval.planner import CurriculumPlanner
from retrieval.agents import CurriculumCriticAgent

log = logging.getLogger("lumina.orchestrator")


class RetrievalService:
    def __init__(self):
        self.paths: Dict[str, MasterLearningPath] = {}
        self.search_provider = YtDlpSearchProvider()
        self.transcript_providers = [
            YtDlpTranscriptProvider(),
        ]
        self.web_provider = WebSearchProvider()
        self.book_provider = MultiSourceBookProvider()
        self.vector_store = VectorStore()
        self.llm = LLMClient()
        self.planner = CurriculumPlanner(self.llm)

    _BEGINNER_MARKERS = ("beginner", "noob", "for beginners", "101", "basics",
                          "introduction", "getting started", "easy", "crash course")
    _ADVANCED_MARKERS = ("advanced", "expert", "master", "pro tips",
                          "internals", "optimization")

    def _level_query_modifier(self, level: UserExpertise) -> str:
        return {
            UserExpertise.BEGINNER: "for beginners introduction basics",
            UserExpertise.INTERMEDIATE: "intermediate techniques",
            UserExpertise.EXPERT: "advanced expert level techniques",
        }.get(level, "")

    def _level_mismatch(self, level: UserExpertise, title: str) -> bool:
        t = title.lower()
        if level == UserExpertise.EXPERT and any(m in t for m in self._BEGINNER_MARKERS):
            return True
        if level == UserExpertise.BEGINNER and any(m in t for m in self._ADVANCED_MARKERS):
            return True
        return False

    def _get_video_segments(self, main_topic: str, sub_topic: str = "", role: ContentRole = ContentRole.FOUNDATIONAL,
                             num_videos: int = 2, seen_urls: Optional[set] = None, level: str = "intermediate",
                             llm: "LLMClient" = None) -> List[PathResource]:
        if num_videos <= 0:
            return []

        if seen_urls is None:
            seen_urls = set()

        if isinstance(sub_topic, ContentRole) or "ContentRole" in str(sub_topic) or not str(sub_topic).strip():
            clean_subtopic = main_topic
        else:
            clean_subtopic = str(sub_topic).strip()

        search_query = f"{main_topic} {clean_subtopic}".strip()
        resources = []

        try:
            results = self.search_provider.search(search_query, max_results=(num_videos * 4) + 1)
            for video in results:
                if len(resources) >= num_videos:
                    break
                if video.url in seen_urls:
                    continue

                active_llm = llm if llm is not None else self.llm
                title_score, reason = active_llm.score_for_role(clean_subtopic, role, video.title)
                if title_score < 0.6:
                    log.info(f"Skipped off-topic video '{video.title}' for subtopic '{clean_subtopic}'")
                    continue

                dynamic_rating = round(3.8 + (title_score * 1.2), 1)

                seen_urls.add(video.url)
                resources.append(PathResource(
                    resource_type=ResourceType.VIDEO_SEGMENT,
                    title=video.title,
                    url=f"{video.url}&t=0s",
                    role=role,
                    justification=reason if reason else f"Targeted explanation for {clean_subtopic}.",
                    rating=dynamic_rating,
                    source_platform="YouTube",
                    start_time=0.0,
                    end_time=600.0
                ))
        except Exception as e:
            log.warning(f"Video search error for '{search_query}': {e}")

        if not resources:
            fallback_query = search_query.replace(' ', '+')
            fallback_url = f"https://www.youtube.com/results?search_query={fallback_query}"
            if fallback_url not in seen_urls:
                seen_urls.add(fallback_url)
                resources.append(PathResource(
                    resource_type=ResourceType.VIDEO_SEGMENT,
                    title=f"Search Videos: {clean_subtopic}",
                    url=fallback_url,
                    role=role,
                    justification=f"Explore community tutorials for {clean_subtopic}.",
                    rating=4.0,
                    source_platform="YouTube Search"
                ))

        return resources

    def _get_text_or_book_resource(self, main_topic: str, sub_topic: str, role: ContentRole, num_texts: int, seen_urls: set) -> List[PathResource]:
        if num_texts <= 0:
            return []

        resources = []
        cleaned_query = f"{main_topic} {sub_topic}".replace("Platform", "").replace("Overview", "").replace("Introduction to", "").strip()

        try:
            books = []
            if hasattr(self.book_provider, "search"):
                books = self.book_provider.search(cleaned_query, limit=num_texts)
            elif hasattr(self.book_provider, "search_books"):
                books = self.book_provider.search_books(cleaned_query, limit=num_texts)
            elif hasattr(self.book_provider, "fetch_books"):
                books = self.book_provider.fetch_books(cleaned_query, limit=num_texts)

            for book in books:
                if len(resources) >= num_texts:
                    break
                if book.url not in seen_urls:
                    seen_urls.add(book.url)
                    book.role = role
                    if not getattr(book, "rating", None):
                        book.rating = 4.5
                    resources.append(book)
        except Exception as e:
            log.warning(f"Book provider search error for '{cleaned_query}': {e}")

        if len(resources) < num_texts:
            try:
                texts = self.web_provider.search_text_resources(cleaned_query, role)
                for t in texts:
                    if len(resources) >= num_texts:
                        break
                    if t.url not in seen_urls:
                        seen_urls.add(t.url)
                        if not getattr(t, "rating", None):
                            t.rating = 4.3
                        resources.append(t)
            except Exception as e:
                log.warning(f"Web provider search error for '{cleaned_query}': {e}")

        if not resources:
            formatted_topic = f"{main_topic} {sub_topic}".replace(' ', '+')
            target_url = f"https://www.google.com/search?q={formatted_topic}+official+documentation+guide"

            if target_url not in seen_urls:
                seen_urls.add(target_url)
                resources.append(PathResource(
                    resource_type=ResourceType.DOCUMENTATION,
                    title=f"Search & Study: {sub_topic}",
                    url=target_url,
                    role=role,
                    justification=f"Explore key documentation and articles covering {sub_topic}.",
                    rating=4.0,
                    source_platform="Google Search"
                ))

        return resources

    def generate_custom_path(self, topic: str, level: UserExpertise,
                              preference: ContentPreference,
                              groq_api_key: str = None) -> MasterLearningPath:
        if groq_api_key:
            llm = LLMClient(api_key=groq_api_key)
            planner = CurriculumPlanner(llm)
        else:
            llm = self.llm
            planner = self.planner

        critic_agent = CurriculumCriticAgent(llm)

        # Agent 1: Initial Breakdown by CurriculumPlannerAgent
        sub_topics_data = planner.structural_breakdown(topic, level)

        # Agent 2: Critic Agent Loop (Up to 2 retries on invalid prerequisite structure)
        max_retries = 2
        for attempt in range(max_retries):
            evaluation = critic_agent.evaluate_path(topic, level, sub_topics_data)
            if evaluation.get("is_valid", True):
                log.info(f"Critic Agent approved curriculum path on attempt {attempt + 1}")
                break
            
            critique_note = evaluation.get("feedback", "Adjust prerequisite sequence.")
            log.warning(f"Critic rejected draft (attempt {attempt + 1}): {critique_note}. Re-planning...")
            sub_topics_data = planner.structural_breakdown(topic, level, critique_feedback=critique_note)

        role_sequence = [
            ContentRole.FOUNDATIONAL,
            ContentRole.DEEP_DIVE,
            ContentRole.PRACTICE,
            ContentRole.DEEP_DIVE,
            ContentRole.PRACTICE,
            ContentRole.REFERENCE
        ]

        role_hours_map = {
            ContentRole.FOUNDATIONAL: 1.0,
            ContentRole.DEEP_DIVE: 1.5,
            ContentRole.PRACTICE: 2.5,
            ContentRole.REFERENCE: 0.5
        }

        nodes = []
        seen_urls = set()

        # Agent 3: Retrieval Specialist Phase (Binds video & text links)
        for idx, sub_item in enumerate(sub_topics_data):
            if isinstance(sub_item, dict):
                sub_title = sub_item.get("title", f"Step {idx + 1}")
                # Clean enum conversion (handles hyphenated or spaced inputs)
                step_type_str = str(sub_item.get("step_type", "foundational")).upper().replace("-", "_").replace(" ", "_")
                step_role = getattr(ContentRole, step_type_str, role_sequence[idx % len(role_sequence)])
                num_videos = sub_item.get("recommended_videos", 2 if step_role == ContentRole.PRACTICE else 1)
                num_texts = sub_item.get("recommended_texts", 1)
                custom_minutes = sub_item.get("estimated_minutes")
                rationale = sub_item.get("resource_rationale", "")
            else:
                sub_title = str(sub_item)
                step_role = role_sequence[idx % len(role_sequence)]
                num_videos = 2 if step_role == ContentRole.PRACTICE else 1
                num_texts = 1
                custom_minutes = None
                rationale = ""

            pref_name = getattr(preference, "name", str(preference)).upper()
            if any(k in pref_name for k in ("TEXT", "BOOK", "READ", "DOC")):
                num_texts = max(num_texts, 2)
                num_videos = 0
            elif "VIDEO" in pref_name and "TEXT" not in pref_name:
                num_videos = max(num_videos, 2)
                num_texts = 0

            collected_resources = []

            if num_videos > 0:
                videos = self._get_video_segments(
                    main_topic=topic,
                    sub_topic=sub_title,
                    role=step_role,
                    num_videos=num_videos,
                    seen_urls=seen_urls,
                    level=level,
                    llm=llm
                )
                collected_resources.extend(videos)

            if num_texts > 0:
                texts = self._get_text_or_book_resource(topic, sub_title, step_role, num_texts, seen_urls)
                collected_resources.extend(texts)

            if custom_minutes:
                calculated_minutes = int(custom_minutes)
                calculated_hours = round(calculated_minutes / 60.0, 1)
            else:
                base_time = role_hours_map.get(step_role, 1.0)
                progression_factor = 1.0 + (idx * 0.08)
                resource_time_add = (len(collected_resources) - 1) * 0.25
                calculated_hours = round(min(5.0, max(0.5, (base_time * progression_factor) + resource_time_add)), 1)
                calculated_minutes = round(calculated_hours * 60)

            node = CurriculumNode(
                topic_title=sub_title,
                role=step_role,
                estimated_hours=calculated_hours,
                estimated_minutes=calculated_minutes,
                resources=collected_resources,
                resource_rationale=rationale
            )

            nodes.append(node)

        related_topics = planner.generate_related_topics(topic, sub_topics_data)

        path = MasterLearningPath(
            main_topic=topic,
            expertise_level=level,
            preference=preference,
            steps=nodes,
            related_topics=related_topics
        )
        self.paths[topic] = path
        return path

    def update_step_status(self, topic: str, step_index: int, new_status: CompletionStatus) -> bool:
        if topic not in self.paths:
            return False

        path = self.paths[topic]
        if 0 <= step_index < len(path.steps):
            path.steps[step_index].status = new_status
            return True

        return False