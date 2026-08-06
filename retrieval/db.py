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
        # Table for storing active user sessions and conversation history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                state_json TEXT NOT NULL
            )
        """)
        # Table for caching transcript searches to avoid hitting YouTube APIs repeatedly
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcript_cache (
                video_id TEXT PRIMARY KEY,
                transcript_json TEXT NOT NULL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

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