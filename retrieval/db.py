import sqlite3
import json
import logging
from retrieval.schemas import MasterLearningPath
from retrieval.chat_agent import ChatSessionState

log = logging.getLogger("lumina.db")
DB_PATH = "lumina_sessions.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                state_json TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcript_cache (
                video_id TEXT PRIMARY KEY,
                transcript_json TEXT NOT NULL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()

def save_groq_key(api_key: str):
    if not api_key or not api_key.strip():
        return
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_config (key, value) VALUES ('groq_api_key', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (api_key.strip(),))
        conn.commit()

def load_groq_key() -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_config WHERE key = 'groq_api_key'")
        row = cursor.fetchone()
        if row:
            return row[0]
    return None

def save_session(session_id: str, session_state: ChatSessionState):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        data = session_state.model_dump_json()
        cursor.execute("""
            INSERT INTO sessions (session_id, state_json) VALUES (?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                updated_at=CURRENT_TIMESTAMP,
                state_json=excluded.state_json
        """, (session_id, data))
        conn.commit()

def load_session(session_id: str) -> ChatSessionState | None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT state_json FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if row:
            return ChatSessionState.model_validate_json(row[0])
    return None