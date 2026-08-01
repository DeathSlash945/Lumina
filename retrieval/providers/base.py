from abc import ABC, abstractmethod
from retrieval.schemas import VideoMeta, TranscriptSegment


class TranscriptUnavailable(Exception):
    """Raised when a provider cannot get captions for a video (no captions,
    age-restricted, region-locked, etc). Orchestrator catches this and
    either falls back to the next provider or skips the video."""
    pass


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int) -> list[VideoMeta]:
        ...


class TranscriptProvider(ABC):
    @abstractmethod
    def get_transcript(self, video_id: str) -> list[TranscriptSegment]:
        ...
