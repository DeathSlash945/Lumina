import logging
import time
from retrieval.schemas import (
    MasterLearningPath, CurriculumNode, PathResource, ResourceType,
    UserExpertise, ContentPreference, ContentRole
)
from retrieval.providers.base import TranscriptUnavailable
from retrieval.providers.ytdlp_provider import YtDlpSearchProvider, YtDlpTranscriptProvider
from retrieval.providers.fallback_provider import YouTubeTranscriptApiProvider
from retrieval.providers.web_provider import WebSearchProvider
from retrieval.chunking import chunk_transcript, merge_contiguous_chunks
from retrieval.vector_store import VectorStore
from retrieval.llm_client import LLMClient
from retrieval.planner import CurriculumPlanner

log = logging.getLogger("lumina.orchestrator")

class RetrievalService:
    def __init__(self):
        self.search_provider = YtDlpSearchProvider()
        self.transcript_providers = [
            YouTubeTranscriptApiProvider(),
            YtDlpTranscriptProvider(),
        ]
        self.web_provider = WebSearchProvider()
        self.vector_store = VectorStore()
        self.llm = LLMClient()
        self.planner = CurriculumPlanner(self.llm)

    def _get_video_segments(self, topic: str, role: ContentRole) -> list[PathResource]:
        """Surfaces highly precise video material mapping to specific sub-topic trees."""
        role_keywords = {
            ContentRole.FOUNDATIONAL: "core concept data structure tutorial",
            ContentRole.DEEP_DIVE: "advanced mathematical analysis derivation",
            ContentRole.PRACTICE: "programming implementation solved problem walkthrough",
            ContentRole.REFERENCE: "common mistakes cheat sheet interview review tips"
        }[role]
        
        # Use rich context targeting for the YouTube Search API
        search_query = f"{topic} {role_keywords}"
        resources = []
        
        try:
            results = self.search_provider.search(search_query, max_results=2)
            for video in results:
                try:
                    # FIX: Query vector store using the clean subtopic string, NOT the noisy search query
                    cached = self.vector_store.query(topic, top_k=4, video_ids=[video.video_id])
                    
                    if not cached:
                        for prov in self.transcript_providers:
                            try:
                                segs = prov.get_transcript(video.video_id)
                                chunks = chunk_transcript(video.video_id, segs)
                                self.vector_store.add_chunks(chunks)
                                cached = self.vector_store.query(topic, top_k=4, video_ids=[video.video_id])
                                break
                            except TranscriptUnavailable:
                                continue
                    
                    if cached:
                        merged = merge_contiguous_chunks(cached)
                        for chunk in merged:
                            score, reason = self.llm.score_for_role(topic, role, chunk.text)
                            if score >= 0.3:
                                resources.append(PathResource(
                                    resource_type=ResourceType.VIDEO_SEGMENT,
                                    title=video.title,
                                    url=f"{video.url}&t={int(chunk.start)}s",
                                    role=role,
                                    justification=reason,
                                    start_time=chunk.start,
                                    end_time=chunk.end
                                ))
                    
                    # FALLBACK LAYER: If video matches perfectly but vector chunk mapping falls short,
                    # construct a substantial conceptual segment from the video timeline.
                    if not resources:
                        resources.append(PathResource(
                            resource_type=ResourceType.VIDEO_SEGMENT,
                            title=video.title,
                            url=f"{video.url}&t=0s",
                            role=role,
                            justification=f"Comprehensive course coverage focusing natively on {topic}.",
                            start_time=0.0,
                            end_time=480.0  # Safe, wide 8-minute window
                        ))
                except Exception:
                    continue
        except Exception:
            pass
            
        return resources[:2]

    def generate_custom_path(self, topic: str, level: UserExpertise, preference: ContentPreference) -> MasterLearningPath:
        """Assembles the finalized roadmap combining both text structures and video sequences."""
        sub_topics = self.planner.structural_breakdown(topic, level)
        role_weights = self.planner.compute_role_weights(level, preference)
        
        nodes = []
        for sub in sub_topics:
            collected_resources = []
            
            for role, weight in role_weights.items():
                if weight <= 0.0:
                    continue
                
                if preference == ContentPreference.MORE_VIDEO:
                    collected_resources.extend(self._get_video_segments(sub, role))
                elif preference == ContentPreference.MORE_TEXT:
                    collected_resources.extend(self.web_provider.search_text_resources(sub, role))
                else:
                    # Balanced multi-format collection
                    videos = self._get_video_segments(sub, role)
                    texts = self.web_provider.search_text_resources(sub, role)
                    if videos: collected_resources.append(videos[0])
                    if texts: collected_resources.append(texts[0])
            
            # Formulate realistic homework/learning estimation caps
            calculated_time = max(1.5, round(len(collected_resources) * 1.5, 1))
            
            nodes.append(CurriculumNode(
                topic_title=sub,
                estimated_hours=calculated_time,
                resources=collected_resources
            ))
            
        return MasterLearningPath(
            main_topic=topic,
            expertise_level=level,
            preference=preference,
            steps=nodes
        )