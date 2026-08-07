import logging
from typing import Dict, List, Set
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

    # Terms that mark a video as belonging to the opposite skill tier.
    _BEGINNER_MARKERS = ("beginner", "noob", "for beginners", "101", "basics",
                          "introduction", "getting started", "easy", "crash course")
    _ADVANCED_MARKERS = ("advanced", "expert", "master", "pro tips",
                          "internals", "architecture", "optimization")

    def _level_query_modifier(self, level: UserExpertise) -> str:
        return {
            UserExpertise.BEGINNER: "for beginners introduction basics",
            UserExpertise.INTERMEDIATE: "intermediate techniques",
            UserExpertise.EXPERT: "advanced expert level techniques",
        }.get(level, "")

    def _level_mismatch(self, level: UserExpertise, title: str) -> bool:
        """True if a video's title clearly targets the wrong skill tier."""
        t = title.lower()
        if level == UserExpertise.EXPERT and any(m in t for m in self._BEGINNER_MARKERS):
            return True
        if level == UserExpertise.BEGINNER and any(m in t for m in self._ADVANCED_MARKERS):
            return True
        return False

    def _get_video_segments(self, main_topic: str, sub_topic: str, role: ContentRole,
                             num_videos: int, seen_urls: set, level: UserExpertise = None,
                             llm: "LLMClient" = None) -> List[PathResource]:
        """Surfaces highly precise video material, strictly bound to the main topic domain and skill level."""
        # Domain-neutral phrasing — avoid tech-flavored terms like "architecture" / "internal
        # mechanics" / "coding", which cause false-positive keyword matches on unrelated topics
        # (e.g. "internal mechanics" pulling in fluid-dynamics videos for a swimming query).
        llm = llm or self.llm
        role_keywords = {
            ContentRole.FOUNDATIONAL: "overview introduction explanation",
            ContentRole.DEEP_DIVE: "in-depth advanced concepts explained",
            ContentRole.PRACTICE: "hands on practice exercise walkthrough",
            ContentRole.REFERENCE: "summary tips review"
        }.get(role, "tutorial guide")

        level_modifier = self._level_query_modifier(level) if level else ""

        # Include main_topic in query to avoid off-topic matches (e.g. fishing gear, trailers)
        search_query = f"{main_topic} {sub_topic} {role_keywords} {level_modifier}".strip()
        resources = []

        # Below this relevance score, a title is treated as an off-topic/junk match and skipped.
        MIN_RELEVANCE = 0.45

        try:
            # Over-fetch more since level-mismatched and low-relevance titles now get filtered out
            results = self.search_provider.search(search_query, max_results=num_videos * 5)
            for video in results:
                if len(resources) >= num_videos:
                    break
                if video.url in seen_urls:
                    continue
                if level and self._level_mismatch(level, video.title):
                    continue

                title_score, reason = llm.score_for_role(sub_topic, role, video.title)
                if title_score < MIN_RELEVANCE:
                    log.info(f"Dropping low-relevance video ({title_score:.2f}) for '{sub_topic}': {video.title}")
                    continue
                score = title_score
                dynamic_rating = round(3.8 + (score * 1.2), 1)

                seen_urls.add(video.url)
                resources.append(PathResource(
                    resource_type=ResourceType.VIDEO_SEGMENT,
                    title=video.title,
                    url=f"{video.url}&t=0s",
                    role=role,
                    justification=reason if reason else f"Key visual explanation for {sub_topic}.",
                    rating=dynamic_rating,
                    source_platform="YouTube",
                    start_time=0.0,
                    end_time=600.0
                ))
        except Exception as e:
            log.warning(f"Video search fallback triggered for '{search_query}': {e}")

        # Safety Fallback
        if not resources:
            fallback_query = f"{main_topic} {sub_topic} {level_modifier}".strip().replace(' ', '+')
            fallback_url = f"https://www.youtube.com/results?search_query={fallback_query}+tutorial"
            if fallback_url not in seen_urls:
                seen_urls.add(fallback_url)
                resources.append(PathResource(
                    resource_type=ResourceType.VIDEO_SEGMENT,
                    title=f"Video Search: {sub_topic}",
                    url=fallback_url,
                    role=role,
                    justification=f"Video resources for {sub_topic}.",
                    rating=4.2,
                    source_platform="YouTube Search"
                ))

        return resources

    def _get_text_or_book_resource(self, main_topic: str, sub_topic: str, role: ContentRole, num_texts: int, seen_urls: set) -> List[PathResource]:
        """Retrieves verified books or text/documentation resources."""
        resources = []
        cleaned_query = f"{main_topic} {sub_topic}".replace("Platform", "").replace("Overview", "").replace("Introduction to", "").strip()

        # MultiSourceBookProvider Search
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

        # Web Documentation/Articles
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

        # Safety Net: Google Search Fallback (Explicitly tagged for frontend topic styling)
        if not resources:
            formatted_topic = f"{main_topic} {sub_topic}".replace(' ', '+')
            target_url = f"https://www.google.com/search?q={formatted_topic}+guide+documentation"

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

        sub_topics_data = self.planner.structural_breakdown(topic, level)

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

        for idx, sub_item in enumerate(sub_topics_data):
            # Parse dict or fallback to string
            if isinstance(sub_item, dict):
                sub_title = sub_item.get("title", f"Step {idx + 1}")
                step_type_str = sub_item.get("step_type", "foundational").upper()
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

            # Apply the user's stated media focus to the LLM-suggested split.
            # ContentPreference is expected to carry values like VIDEO / TEXT / BALANCED.
            pref_name = getattr(preference, "name", str(preference)).upper()
            if "VIDEO" in pref_name and "TEXT" not in pref_name:
                num_videos = max(num_videos, 2)
                num_texts = max(num_texts - 1, 0)
            elif "TEXT" in pref_name or "READ" in pref_name:
                num_texts = max(num_texts, 2)
                num_videos = max(num_videos - 1, 1)
            # BALANCED (or unrecognized): leave the LLM's per-step numbers as-is.

            collected_resources = []

            # Gather dynamic number of videos & text resources
            videos = self._get_video_segments(topic, sub_title, step_role, num_videos,
                                                seen_urls, level=level, llm=llm)
            texts = self._get_text_or_book_resource(topic, sub_title, step_role, num_texts, seen_urls)

            collected_resources.extend(videos)
            collected_resources.extend(texts)

            # Calculate dynamic step duration
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
        """Updates the completion status of a step within an active curriculum path."""
        if topic not in self.paths:
            return False

        path = self.paths[topic]
        if 0 <= step_index < len(path.steps):
            path.steps[step_index].status = new_status
            return True

        return False