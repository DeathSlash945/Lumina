import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# --- Ollama ---
OLLAMA_HOST = os.getenv("LUMINA_OLLAMA_HOST", "http://localhost:11434")
CHAT_MODEL = os.getenv("LUMINA_CHAT_MODEL", "qwen3:8b")
EMBED_MODEL = os.getenv("LUMINA_EMBED_MODEL", "nomic-embed-text")

# --- Storage ---
CHROMA_PATH = str(DATA_DIR / "chroma")
CACHE_DB_PATH = str(DATA_DIR / "cache.sqlite3")

# --- Retrieval tuning ---
MAX_SUBQUERIES_PER_TOPIC = 4
MAX_VIDEOS_PER_SUBQUERY = 4      # was 5 -- fewer candidates = fewer transcript fetches + LLM calls
VECTOR_QUERY_TOP_K = 4           # chunks pulled per role bucket before LLM scoring
MAX_FINAL_SEGMENTS = 8
CHUNK_TARGET_SECONDS = 60
CHUNK_MAX_SECONDS = 90
CHUNK_GAP_THRESHOLD = 2.0
REQUEST_DELAY_SECONDS = 2.5  # politeness delay between yt-dlp calls
