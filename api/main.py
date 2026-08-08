import os
import logging
from urllib.parse import unquote
from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.schemas import CreatePathRequest, ProgressUpdateRequest
from retrieval.schemas import MasterLearningPath, CompletionStatus
from retrieval.orchestrator import RetrievalService
from retrieval.chat_agent import LuminaChatAgent
from retrieval.db import init_db, save_session, load_session, save_groq_key, load_groq_key
from retrieval.progress_tracker import ProgressTracker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lumina.api")

app = FastAPI(title="Lumina Engine")

# init db on app startup
init_db()

# cors configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# start services
service = RetrievalService()
chat_agent = LuminaChatAgent()


class MutatePathRequest(BaseModel):
    topic: str
    message: str


# --- endpoints ---

@app.get("/health")
def health_check():
    return {"status": "online", "engine": "Lumina Engine"}


@app.post(
    "/api/v1/curriculum/generate",
    response_model=MasterLearningPath,
    status_code=status.HTTP_201_CREATED
)
def generate_curriculum(payload: CreatePathRequest):
    """uses the api key and payload given to create the path."""
    if payload.groq_api_key and payload.groq_api_key.strip():
        save_groq_key(payload.groq_api_key)
        active_key = payload.groq_api_key.strip()
    else:
        active_key = load_groq_key()

    if not active_key:
        raise HTTPException(
            status_code=401, 
            detail="No Groq API Key found in database. Please enter a valid API key."
        )
    try:
        path = service.generate_custom_path(
            topic=payload.topic,
            level=payload.expertise_level,
            preference=payload.content_preference,
            groq_api_key=payload.groq_api_key
        )
        
        # save session for chat agent mutations
        clean_topic = payload.topic.strip()
        lower_key = clean_topic.lower()
        
        session_state = chat_agent.initialize_session(
            topic=payload.topic,
            level=payload.expertise_level,
            pref=payload.content_preference,
        )
        session_state.current_path = path
        
        save_session(lower_key, session_state)
        save_session(clean_topic, session_state)
        
        return path
    except Exception as e:
        log.error(f"failed to generate curriculum: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/curriculum/mutate")
def mutate_curriculum(req: MutatePathRequest):
    """accepts natural language prompts to dynamically alter the current path."""
    clean_topic = unquote(req.topic).strip()
    key = clean_topic.lower()

    session = load_session(key) or load_session(clean_topic)
    if not session:
        session = chat_agent.initialize_session(topic=clean_topic)

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
def update_progress(topic: str, payload: ProgressUpdateRequest):
    """updates step progress with fallback to session store if service cache is cleared."""
    clean_topic = unquote(topic).strip()
    lower_key = clean_topic.lower()

    success = service.update_step_status(lower_key, payload.step_index, payload.status) or \
              service.update_step_status(clean_topic, payload.step_index, payload.status)

    if not success:
        session = load_session(lower_key) or load_session(clean_topic)
        if session and session.current_path:
            session.current_path = ProgressTracker.update_step_status(
                session.current_path, payload.step_index, payload.status
            )
            save_session(lower_key, session)
            success = True

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Topic '{topic}' or step index {payload.step_index} not found."
        )

    return {"status": "updated", "topic": clean_topic, "step_index": payload.step_index, "new_status": payload.status}


@app.get("/api/v1/curriculum/{topic}", response_model=MasterLearningPath)
def get_curriculum(topic: str):
    """retrieves generated curriculum path by topic."""
    clean_topic = unquote(topic).strip()
    lower_key = clean_topic.lower()

    session = load_session(lower_key) or load_session(clean_topic)
    if session and session.current_path:
        return session.current_path

    if lower_key in service.paths:
        return service.paths[lower_key]

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Curriculum path for topic '{topic}' not found."
    )


# mount static frontend files (must stay at bottom after all api endpoints)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")