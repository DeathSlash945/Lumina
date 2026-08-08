import sqlite3
import os
import json
import logging
from retrieval.schemas import MasterLearningPath
from retrieval.chat_agent import ChatSessionState

log = logging.getLogger("lumina.db")
DB_PATH = os.getenv("LUMINA_DB_PATH", "lumina_sessions.db")
_db_dir = os.path.dirname(DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

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

        env_key = os.getenv("GROQ_API_KEY", "").strip()
        if env_key and not load_groq_key():
            save_groq_key(env_key)

def save_groq_key(api_key: str):
    if not api_key or not api_key.strip():
        return
    api_key = api_key.strip()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_config (key, value) VALUES ('groq_api_key', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (api_key,))
        conn.commit()
    # retrieval.llm reads GROQ_API_KEY straight from the environment, not the DB -
    # without this, a key saved via the UI/DB is silently invisible to it.
    os.environ["GROQ_API_KEY"] = api_key

def load_groq_key() -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_config WHERE key = 'groq_api_key'")
        row = cursor.fetchone()
        if row:
            os.environ["GROQ_API_KEY"] = row[0]
            return row[0]
    return os.getenv("GROQ_API_KEY", "").strip() or None

def clear_groq_key():
    """Removes the DB-stored key and unsets it from the environment."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM app_config WHERE key = 'groq_api_key'")
        conn.commit()
    os.environ.pop("GROQ_API_KEY", None)

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