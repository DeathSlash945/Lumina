import json
import sqlite3
import time
from contextlib import contextmanager
from config import CACHE_DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    video_id TEXT PRIMARY KEY,
    segments_json TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS video_meta (
    video_id TEXT PRIMARY KEY,
    meta_json TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(CACHE_DB_PATH)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


class TranscriptCache:
    def get_transcript(self, video_id: str) -> list[dict] | None:
        with _connect() as conn:
            row = conn.execute(
                "SELECT segments_json FROM transcripts WHERE video_id = ?", (video_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def store_transcript(self, video_id: str, segments: list[dict]):
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO transcripts (video_id, segments_json, fetched_at) VALUES (?, ?, ?)",
                (video_id, json.dumps(segments), time.time()),
            )

    def get_video_meta(self, video_id: str) -> dict | None:
        with _connect() as conn:
            row = conn.execute(
                "SELECT meta_json FROM video_meta WHERE video_id = ?", (video_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def store_video_meta(self, video_id: str, meta: dict):
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO video_meta (video_id, meta_json, fetched_at) VALUES (?, ?, ?)",
                (video_id, json.dumps(meta), time.time()),
            )
