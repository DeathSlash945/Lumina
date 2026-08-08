# Pydantic models shared across.
from __future__ import annotations
from enum import Enum
from typing import Optional, Literal, Union, Dict, Any, List
from pydantic import BaseModel, Field

# --- User preference types ---
class UserExpertise(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"

class ContentPreference(str, Enum):
    MORE_TEXT = "more_text"
    MORE_VIDEO = "more_video"
    BALANCED = "balanced"

class ContentRole(str, Enum):
    """Pedagogical roles mapped to structural positions in a path."""
    FOUNDATIONAL = "foundational"   # Beginner introduction / concepts
    DEEP_DIVE = "deep_dive"         # Mathematical derivation or architectural breakdown
    PRACTICE = "practice"           # Hands on problem sets or walkthroughs
    REFERENCE = "reference"         # API documentation, cheat-sheets, edge cases

class ResourceType(str, Enum):
    VIDEO_SEGMENT = "video_segment"
    BOOK = "book"
    ARTICLE = "article"
    TEXT = "text"
    DOCUMENTATION = "documentation"
    WEB = "web"

class CompletionStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

# --- Unified resource containers ---
class PathResource(BaseModel):
    """A unified resource wrapper capable of tracking videos, books, or web docs."""
    resource_type: ResourceType
    title: str
    url: str
    role: ContentRole
    justification: str
    # Video-specific markers
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    # Text-specific markers
    reading_time_minutes: Optional[int] = None
    source_domain: Optional[str] = None
    status: CompletionStatus = CompletionStatus.NOT_STARTED
    rating: float = Field(default=4.5, ge=0.0, le=5.0, description="Curated or API rating out of 5")
    source_platform: str = Field(default="Web", description="e.g. Google Books, Open Library, YouTube, ArXiv")
    author_or_channel: str = Field(default="Unknown", description="Creator, Publisher, or Channel name")

class VideoMeta(BaseModel):
    video_id: str
    title: str
    channel: Optional[str] = None
    duration_seconds: Optional[int] = None
    view_count: Optional[int] = None
    url: str

class TranscriptSegment(BaseModel):
    text: str
    start: float
    duration: float

class TranscriptChunk(BaseModel):
    video_id: str
    chunk_id: str
    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

# --- Final path entities ---
class CurriculumNode(BaseModel):
    topic_title: str
    estimated_hours: float
    estimated_minutes: Optional[int] = None
    role: ContentRole = ContentRole.FOUNDATIONAL
    resources: list[PathResource]
    status: CompletionStatus = CompletionStatus.NOT_STARTED
    resource_rationale: Optional[str] = ""
    
    @property
    def progress_percentage(self) -> float:
        if not self.resources:
            return 100.0 if self.status == CompletionStatus.COMPLETED else 0.0
        completed = sum(1 for r in self.resources if r.status == CompletionStatus.COMPLETED)
        return round((completed / len(self.resources)) * 100.0, 1)

# main learning path scheme
class MasterLearningPath(BaseModel):
    main_topic: str
    expertise_level: UserExpertise
    preference: ContentPreference
    steps: list[CurriculumNode]
    related_topics: list[str] = Field(default_factory=list)
    
    @property
    def total_progress(self) -> float:
        if not self.steps:
            return 0.0
        total_resources = sum(len(s.resources) for s in self.steps)
        if total_resources == 0:
            return 0.0
        completed_resources = sum(
            sum(1 for r in s.resources if r.status == CompletionStatus.COMPLETED)
            for s in self.steps
        )
        return round((completed_resources / total_resources) * 100.0, 1)

# --- Chat & Session State Schemas ---
class ChatMessage(BaseModel):
    role: str
    content: Union[str, Dict[str, Any], List[Any]]

class ChatSessionState(BaseModel):
    topic: Optional[str] = ""
    current_path: MasterLearningPath
    conversation_history: List[Union[ChatMessage, Dict[str, Any], str]] = Field(default_factory=list)