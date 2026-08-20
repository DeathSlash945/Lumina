import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from retrieval.schemas import MasterLearningPath
from retrieval.chat_agent import ChatSessionState

log = logging.getLogger("lumina.db")

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # sessions: state_json upgraded to JSONB
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    state_json JSONB NOT NULL
                );
            """)
            # transcript_cache: transcript_json upgraded to JSONB
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcript_cache (
                    video_id TEXT PRIMARY KEY,
                    transcript_json JSONB NOT NULL,
                    cached_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            conn.commit()

    env_key = os.getenv("GROQ_API_KEY", "").strip()
    if env_key and not load_groq_key():
        save_groq_key(env_key)

def save_groq_key(api_key: str):
    if not api_key or not api_key.strip():
        return
    api_key = api_key.strip()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # PostgreSQL upsert syntax using EXCLUDED
            cursor.execute("""
                INSERT INTO app_config (key, value) VALUES ('groq_api_key', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """, (api_key,))
            conn.commit()
    
    os.environ["GROQ_API_KEY"] = api_key

def load_groq_key() -> str | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT value FROM app_config WHERE key = 'groq_api_key';")
            row = cursor.fetchone()
            if row:
                os.environ["GROQ_API_KEY"] = row[0]
                return row[0]
    return os.getenv("GROQ_API_KEY", "").strip() or None

def clear_groq_key():
    """Removes the DB-stored key and unsets it from the environment."""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM app_config WHERE key = 'groq_api_key';")
            conn.commit()
    os.environ.pop("GROQ_API_KEY", None)

def save_session(session_id: str, session_state: ChatSessionState):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            data = session_state.model_dump_json()
            cursor.execute("""
                INSERT INTO sessions (session_id, state_json) VALUES (%s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    updated_at = CURRENT_TIMESTAMP,
                    state_json = EXCLUDED.state_json;
            """, (session_id, data))
            conn.commit()

def load_session(session_id: str) -> ChatSessionState | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT state_json FROM sessions WHERE session_id = %s;", (session_id,))
            row = cursor.fetchone()
            if row:
                # row[0] is automatically parsed from JSONB to dict/str by psycopg2
                raw_json = row[0]
                if isinstance(raw_json, dict):
                    return ChatSessionState.model_validate(raw_json)
                return ChatSessionState.model_validate_json(raw_json)
    return None