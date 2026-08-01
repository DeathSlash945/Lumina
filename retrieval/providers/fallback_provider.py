"""
Fallback transcript provider. youtube-transcript-api is lighter and faster
than yt-dlp when it works, so we try it as a quick first attempt in the
orchestrator's fallback chain -- but it's currently more exposed to
YouTube's PoToken bot-detection rollout, so yt-dlp remains primary.
"""
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

from retrieval.providers.base import TranscriptProvider, TranscriptUnavailable
from retrieval.schemas import TranscriptSegment


class YouTubeTranscriptApiProvider(TranscriptProvider):
    def get_transcript(self, video_id: str) -> list[TranscriptSegment]:
        try:
            raw = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            raise TranscriptUnavailable(str(e)) from e
        except Exception as e:
            # Covers PoToken/bot-detection failures, rate limits, etc.
            raise TranscriptUnavailable(f"youtube-transcript-api failed: {e}") from e

        segments = [
            TranscriptSegment(text=item.text, start=item.start, duration=item.duration)
            for item in raw
            if item.text.strip()
        ]
        if not segments:
            raise TranscriptUnavailable(f"Empty transcript for {video_id}")
        return segments
