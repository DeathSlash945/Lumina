import logging
import os
import urllib.parse
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from retrieval.schemas import (
    MasterLearningPath,
    UserExpertise,
    ContentPreference,
    CompletionStatus,
)
from retrieval.chat_agent import LuminaChatAgent
from retrieval.db import (
    init_db,
    save_session,
    load_session,
    save_groq_key,
    load_groq_key,
    clear_groq_key,
)
from retrieval.progress_tracker import ProgressTracker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lumina.api")


# init db on app startup via lifespan (replaces the old module-level init_db() call)
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Project Lumina Engine",
    description="Automated, personalized learning path generator and stateful curriculum assistant.",
    version="1.0.0",
    lifespan=lifespan,
)

# cors configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_agent = LuminaChatAgent()


# --- request schemas ---
# (kept inline here rather than pulled from a separate api/schemas module,
# since that module wasn't part of what was shared and this keeps main.py
# self-contained)

class GenerateCurriculumRequest(BaseModel):
    topic: str
    expertise_level: UserExpertise = UserExpertise.INTERMEDIATE
    content_preference: ContentPreference = ContentPreference.BALANCED
    groq_api_key: str | None = None


class UpdateProgressRequest(BaseModel):
    step_index: int
    status: CompletionStatus


class MutatePathRequest(BaseModel):
    topic: str
    message: str


class GroqKeyRequest(BaseModel):
    groq_api_key: str


# --- session lookup helpers ---

def _candidate_keys(topic_raw: str) -> list[str]:
    decoded = urllib.parse.unquote(topic_raw).strip()
    # de-dupe while preserving order, since topic_raw and decoded are
    # often identical and there's no point trying the same key twice
    seen = []
    for k in (decoded, decoded.lower(), topic_raw, topic_raw.lower()):
        if k not in seen:
            seen.append(k)
    return seen


def _find_session(topic_raw: str):
    """Lookup-only: returns (key, session) or (None, None) if nothing is stored yet."""
    for k in _candidate_keys(topic_raw):
        session = load_session(k)
        if session:
            return k, session
    return None, None


def _get_or_create_session(topic_raw: str):
    """Lookup, falling back to creating a fresh session if none exists."""
    key, session = _find_session(topic_raw)
    if session:
        return key, session

    decoded = urllib.parse.unquote(topic_raw).strip()
    new_session = chat_agent.initialize_session(topic=decoded)
    save_session(decoded.lower(), new_session)
    return decoded.lower(), new_session


# --- health ---

@app.get("/health")
def health_check():
    return {"status": "online", "engine": "Project Lumina RAG Engine"}


# --- groq api key config ---

@app.post("/api/v1/config/groq-key")
def set_groq_key_endpoint(req: GroqKeyRequest):
    if not req.groq_api_key or not req.groq_api_key.strip():
        raise HTTPException(status_code=400, detail="API key cannot be empty.")
    save_groq_key(req.groq_api_key.strip())
    return {"status": "success", "message": "Groq API key saved."}


@app.get("/api/v1/config/groq-key")
def get_groq_key_status():
    return {"has_key": bool(load_groq_key())}


@app.delete("/api/v1/config/groq-key")
def clear_groq_key_endpoint():
    clear_groq_key()
    return {"status": "success", "message": "Groq API key cleared."}


# --- curriculum endpoints ---

@app.post(
    "/api/v1/curriculum/generate",
    response_model=MasterLearningPath,
    status_code=status.HTTP_201_CREATED,
)
def generate_curriculum(req: GenerateCurriculumRequest):
    """Generates a learning path and stores the chat session around it.

    NOTE on a fix vs. the old api/main.py: that version generated the path
    twice - once via RetrievalService.generate_custom_path(), and again via
    chat_agent.initialize_session() (whose result was then thrown away except
    for its session wrapper). chat_agent.initialize_session() already does
    the generation, so this now calls it exactly once.
    """
    if req.groq_api_key and req.groq_api_key.strip():
        save_groq_key(req.groq_api_key.strip())

    active_key = load_groq_key()
    if not active_key:
        raise HTTPException(
            status_code=401,
            detail="No Groq API key found. Please enter your key.",
        )

    try:
        session_state = chat_agent.initialize_session(
            topic=req.topic,
            level=req.expertise_level,
            pref=req.content_preference,
        )

        raw_key = req.topic.strip()
        lower_key = raw_key.lower()

        save_session(lower_key, session_state)
        if lower_key != raw_key:
            save_session(raw_key, session_state)

        return session_state.current_path
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"failed to generate curriculum for topic '{req.topic}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Curriculum generation failed: {str(e)}",
        )


@app.post("/api/v1/curriculum/mutate")
def mutate_curriculum(req: MutatePathRequest):
    """Accepts natural language prompts to dynamically alter the current path."""
    key, session = _get_or_create_session(req.topic)
    try:
        response_text, updated_session = chat_agent.process_message(
            session=session,
            user_message=req.message,
        )
        save_session(key, updated_session)

        return {
            "response": response_text,
            "path": updated_session.current_path,
        }
    except Exception as e:
        log.error(f"failed to mutate curriculum for '{req.topic}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Path mutation failed: {str(e)}",
        )


@app.patch("/api/v1/curriculum/{topic}/progress")
def update_step_progress(topic: str, req: UpdateProgressRequest):
    """Updates the completion status of a specific step in an active curriculum."""
    key, session = _get_or_create_session(topic)

    if not session.current_path or not session.current_path.steps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No steps available in learning path for topic '{topic}'.",
        )

    if req.step_index < 0 or req.step_index >= len(session.current_path.steps):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Step index {req.step_index} out of bounds for topic '{topic}'.",
        )

    session.current_path = ProgressTracker.update_step_status(
        session.current_path, req.step_index, req.status
    )
    save_session(key, session)

    return {
        "status": "success",
        "topic": topic,
        "step_index": req.step_index,
        "new_status": req.status,
    }


@app.get("/api/v1/curriculum/{topic}", response_model=MasterLearningPath)
def get_curriculum(topic: str):
    """Retrieves an existing generated curriculum path by topic.

    NOTE on a fix vs. the old root main.py: that version used
    _get_or_create_session() here too, which meant a GET request for an
    unknown topic silently triggered a full (auto-)generation as a side
    effect - surprising for a read-only endpoint and an unnecessary LLM call.
    This now does a lookup-only fetch and returns 404 if nothing is stored.
    """
    _, session = _find_session(topic)
    if not session or not session.current_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curriculum path for topic '{topic}' not found.",
        )
    return session.current_path


# mount static frontend files (must stay at bottom, after all API routes,
# so it doesn't shadow them)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")