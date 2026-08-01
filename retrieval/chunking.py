"""
Semantic chunking engine with dynamic context window expansion.
"""
import uuid
from retrieval.schemas import TranscriptSegment, TranscriptChunk
from config import CHUNK_TARGET_SECONDS, CHUNK_MAX_SECONDS, CHUNK_GAP_THRESHOLD

def chunk_transcript(
    video_id: str,
    segments: list[TranscriptSegment],
    target_window: float = CHUNK_TARGET_SECONDS,
    max_window: float = CHUNK_MAX_SECONDS,
    gap_threshold: float = CHUNK_GAP_THRESHOLD,
) -> list[TranscriptChunk]:
    if not segments:
        return []

    chunks: list[TranscriptChunk] = []
    current: list[TranscriptSegment] = []
    current_start = segments[0].start

    def flush(bucket: list[TranscriptSegment], start_time: float):
        if not bucket:
            return
        end_time = bucket[-1].start + bucket[-1].duration
        text = " ".join(s.text for s in bucket)
        chunks.append(TranscriptChunk(
            video_id=video_id,
            chunk_id=str(uuid.uuid4())[:8],
            text=text,
            start=start_time,
            end=end_time,
        ))

    for seg in segments:
        if current:
            prev = current[-1]
            gap = seg.start - (prev.start + prev.duration)
            elapsed = seg.start - current_start

            hit_natural_break = gap > gap_threshold and elapsed >= target_window * 0.5
            hit_hard_ceiling = elapsed >= max_window

            if hit_natural_break or hit_hard_ceiling:
                flush(current, current_start)
                current = []
                current_start = seg.start

        current.append(seg)

    flush(current, current_start)
    return chunks

def merge_contiguous_chunks(chunks: list[TranscriptChunk], gap_tolerance: float = 45.0) -> list[TranscriptChunk]:
    """
    Implements a growing outward chunking mechanism.
    If chunks are within the gap_tolerance window, they expand outward
    to capture a complete, meaningful conceptual sequence.
    """
    if not chunks:
        return []

    by_video: dict[str, list[TranscriptChunk]] = {}
    for c in chunks:
        by_video.setdefault(c.video_id, []).append(c)

    merged: list[TranscriptChunk] = []
    for video_id, vid_chunks in by_video.items():
        vid_chunks.sort(key=lambda c: c.start)
        bucket = [vid_chunks[0]]
        
        for c in vid_chunks[1:]:
            # Dynamic check: If the gap is small enough, expand the current window outward
            if c.start - bucket[-1].end <= gap_tolerance:
                bucket.append(c)
            else:
                merged.append(_merge_bucket(bucket))
                bucket = [c]
        merged.append(_merge_bucket(bucket))
        
    return merged

def _merge_bucket(bucket: list[TranscriptChunk]) -> TranscriptChunk:
    # Build an expanded context block ensuring complete explanations are not cut short
    start_time = max(0.0, bucket[0].start - 15.0)  # Pad 15s backward for context safety
    end_time = bucket[-1].end + 20.0               # Pad 20s forward for natural wrap-ups
    
    return TranscriptChunk(
        video_id=bucket[0].video_id,
        chunk_id=str(uuid.uuid4())[:8],
        text=" ".join(c.text for c in bucket),
        start=start_time,
        end=end_time,
    )