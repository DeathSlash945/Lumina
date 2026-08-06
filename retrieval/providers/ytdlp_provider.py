"""
Primary retrieval provider. yt-dlp is preferred over youtube-transcript-api
as the default because it's more actively maintained against YouTube's
bot-detection changes and gives us search + metadata + captions from one
tool, with no quota (unlike the official Data API).
"""
import time
import requests
import yt_dlp

from retrieval.providers.base import SearchProvider, TranscriptProvider, TranscriptUnavailable
from retrieval.schemas import VideoMeta, TranscriptSegment

CAPTION_FETCH_RETRIES = 3
CAPTION_FETCH_BACKOFF_BASE = 3.0  # seconds; doubles each retry
params = {
    "relevanceLanguage": "en",
    "type": "video",
}

def _fetch_caption_json(url: str) -> dict:
    """GET the caption track with retry+backoff on 429s. YouTube rate-limits
    this endpoint aggressively when hit repeatedly in a short window, which
    is exactly what indexing several candidate videos back-to-back does."""
    last_error = None
    for attempt in range(CAPTION_FETCH_RETRIES):
        resp = requests.get(url, timeout=15)
        if resp.status_code == 429:
            wait = CAPTION_FETCH_BACKOFF_BASE * (2 ** attempt)
            last_error = f"429 rate-limited (attempt {attempt + 1}/{CAPTION_FETCH_RETRIES})"
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise TranscriptUnavailable(f"Caption fetch rate-limited after {CAPTION_FETCH_RETRIES} attempts: {last_error}")


def _base_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }


class YtDlpSearchProvider(SearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[VideoMeta]:
        opts = _base_opts() | {"extract_flat": "in_playlist"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)

        videos = []
        for entry in result.get("entries", []) or []:
            if not entry or not entry.get("id"):
                continue
            videos.append(VideoMeta(
                video_id=entry["id"],
                title=entry.get("title", "Untitled"),
                channel=entry.get("channel") or entry.get("uploader"),
                duration_seconds=entry.get("duration"),
                view_count=entry.get("view_count"),
                url=f"https://www.youtube.com/watch?v={entry['id']}",
            ))
        return videos


class YtDlpTranscriptProvider(TranscriptProvider):
    """Pulls auto/manual captions via yt-dlp, in json3 format, and flattens
    them into plain timed segments."""

    def get_transcript(self, video_id: str) -> list[TranscriptSegment]:
        opts = _base_opts() | {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en"],
            "subtitlesformat": "json3",
        }
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            raise TranscriptUnavailable(f"yt-dlp extraction failed for {video_id}: {e}") from e

        caption_tracks = (info.get("subtitles") or {}).get("en") \
            or (info.get("automatic_captions") or {}).get("en")

        if not caption_tracks:
            raise TranscriptUnavailable(f"No English captions for {video_id}")

        json3_entry = next((f for f in caption_tracks if f.get("ext") == "json3"), None)
        if not json3_entry:
            raise TranscriptUnavailable(f"No json3 caption track for {video_id}")

        try:
            data = _fetch_caption_json(json3_entry["url"])
        except requests.exceptions.RequestException as e:
            raise TranscriptUnavailable(f"Caption fetch failed for {video_id}: {e}") from e

        segments: list[TranscriptSegment] = []
        for event in data.get("events", []):
            segs = event.get("segs")
            if not segs:
                continue
            text = "".join(s.get("utf8", "") for s in segs).strip()
            if not text:
                continue
            segments.append(TranscriptSegment(
                text=text,
                start=event.get("tStartMs", 0) / 1000,
                duration=event.get("dDurationMs", 0) / 1000,
            ))

        if not segments:
            raise TranscriptUnavailable(f"Empty transcript for {video_id}")
        return segments
