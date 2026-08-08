import logging
import urllib.parse
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from retrieval.schemas import (
    MasterLearningPath,
    UserExpertise,
    ContentPreference,
    CompletionStatus,
)
from retrieval.chat_agent import LuminaChatAgent
from retrieval.db import init_db, save_session, load_session
from retrieval.progress_tracker import ProgressTracker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lumina.api")


# init db on app startup using lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Project Lumina Engine",
    description="automated, personalized learning path generator and stateful curriculum assistant.",
    version="1.0.0",
    lifespan=lifespan,
)

# enable cors for local ui interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_agent = LuminaChatAgent()


# --- request schemas ---

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


# --- session lookup helper ---

def _get_or_create_session(topic_raw: str):
    decoded = urllib.parse.unquote(topic_raw).strip()
    keys_to_try = [decoded, decoded.lower(), topic_raw, topic_raw.lower()]

    for k in keys_to_try:
        session = load_session(k)
        if session:
            return k, session

    # auto recreate session if missing from db
    new_session = chat_agent.initialize_session(topic=decoded)
    save_session(decoded.lower(), new_session)
    return decoded.lower(), new_session


# --- endpoints ---

@app.get("/health")
def health_check():
    return {"status": "online", "engine": "Project Lumina RAG Engine"}


@app.post("/api/v1/curriculum/generate", response_model=MasterLearningPath)
def generate_curriculum(req: GenerateCurriculumRequest):
    """generates a dynamic learning path based on topic, expertise level, and preferences."""
    try:
        session_state = chat_agent.initialize_session(
            topic=req.topic,
            level=req.expertise_level,
            pref=req.content_preference,
        )
        raw_key = req.topic.strip()
        lower_key = raw_key.lower()

        # save under both raw and lowercase keys to guarantee matching
        save_session(lower_key, session_state)
        save_session(raw_key, session_state)

        return session_state.current_path
    except Exception as e:
        log.error(f"failed to generate curriculum for topic '{req.topic}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Curriculum generation failed: {str(e)}",
        )


@app.post("/api/v1/curriculum/mutate")
def mutate_curriculum(req: MutatePathRequest):
    """accepts natural language prompts to dynamically alter the current path."""
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
    """updates the completion status of a specific step in an active curriculum."""
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
    """retrieves an existing generated curriculum path by topic."""
    _, session = _get_or_create_session(topic)
    return session.current_path