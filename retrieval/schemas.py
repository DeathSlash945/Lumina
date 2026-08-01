"""
Pydantic models shared across the Lumina curriculum and retrieval pipeline.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field

# --- User Preference Types ---
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
    PRACTICE = "practice"           # Hands-on problem sets, code walkthroughs, or labs
    REFERENCE = "reference"         # API documentation, cheat-sheets, edge cases

class ResourceType(str, Enum):
    VIDEO_SEGMENT = "video_segment"
    TEXT_ARTICLE = "text_article"
    BOOK_PART = "book_part"

# --- Unified Resource Containers ---
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

# --- Final Path Entities ---
class CurriculumNode(BaseModel):
    """An individual structural step or structural milestone in the learning path."""
    topic_title: str
    estimated_hours: float
    resources: list[PathResource]

class MasterLearningPath(BaseModel):
    """The globally tracked active path object representing the user's current track."""
    main_topic: str
    expertise_level: UserExpertise
    preference: ContentPreference
    steps: list[CurriculumNode]