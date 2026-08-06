import uuid
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from retrieval.schemas import MasterLearningPath, UserExpertise, ContentPreference, CompletionStatus
from retrieval.chat_agent import LuminaChatAgent
from retrieval.db import init_db, save_session, load_session
from retrieval.progress_tracker import ProgressTracker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lumina.api")


app = FastAPI(
    title="Project Lumina Engine",
    description="Automated, personalized learning path generator and stateful curriculum assistant.",
    version="1.0.0"
)

@app.lifespan("startup")
def startup_event():
    init_db()

# Enable CORS for local UI development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
CHAT_AGENT = LuminaChatAgent()

# --- Request / Response Schemas ---
class GeneratePathRequest(BaseModel):
    topic: str
    expertise_level: UserExpertise = UserExpertise.BEGINNER
    preference: ContentPreference = ContentPreference.BALANCED

class InitSessionResponse(BaseModel):
    session_id: str
    path: MasterLearningPath
    initial_message: str

class ChatMessageRequest(BaseModel):
    session_id: str
    message: str

class ChatMessageResponse(BaseModel):
    session_id: str
    response: str
    updated_path: MasterLearningPath

class UpdateProgressRequest(BaseModel):
    session_id: str
    step_index: int  # 0-indexed
    resource_index: int | None = None  # None if marking whole step
    status: CompletionStatus

class ProgressResponse(BaseModel):
    session_id: str
    step_index: int
    step_progress: float
    total_progress: float
    updated_path: MasterLearningPath
    #___________________________________________________________________________

@app.post("/api/v1/progress/update", response_model=ProgressResponse)
def update_progress(req: UpdateProgressRequest):
    session = load_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    if req.resource_index is not None:
        session.current_path = ProgressTracker.update_resource_status(
            session.current_path, req.step_index, req.resource_index, req.status
        )
    else:
        session.current_path = ProgressTracker.update_step_status(
            session.current_path, req.step_index, req.status
        )
        
    save_session(req.session_id, session)
    
    target_node = session.current_path.steps[req.step_index]
    
    return ProgressResponse(
        session_id=req.session_id,
        step_index=req.step_index,
        step_progress=target_node.progress_percentage,
        total_progress=session.current_path.total_progress,
        updated_path=session.current_path
    )


# --- API Endpoints ---

@app.get("/health")
def health_check():
    return {"status": "online", "engine": "Project Lumina RAG + Agent Controller"}


@app.post("/api/v1/path/generate", response_model=InitSessionResponse)
def generate_path(req: GeneratePathRequest):
    """
    Initializes a new learning session, runs the curriculum planner,
    populates resources via the retrieval orchestrator, and returns a session ID.
    """
    try:
        session_id = str(uuid.uuid4())
        session_state = CHAT_AGENT.initialize_session(
            topic=req.topic,
            level=req.expertise_level,
            pref=req.preference
        )
        save_session(session_id,session_state)
        
        return InitSessionResponse(
            session_id=session_id,
            path=session_state.current_path,
            initial_message=session_state.conversation_history[-1]["content"]
        )
    except Exception as e:
        log.error(f"Failed to generate learning path: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Path generation failed: {str(e)}")


@app.post("/api/v1/chat/mutate", response_model=ChatMessageResponse)
def mutate_path_chat(req: ChatMessageRequest):
    """
    Accepts natural language commands to dynamically mutate, expand, or update
    the current active MasterLearningPath state.
    """
    session_state = load_session(req.session_id)
    if not session_state:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    try:
        response_text, updated_session = CHAT_AGENT.process_message(
            session=session_state,
            user_message=req.message
        )
        
        # Persist updated session state
        save_session(req.session_id, updated_session)
        
        return ChatMessageResponse(
            session_id=req.session_id,
            response=response_text,
            updated_path=updated_session.current_path
        )
    except Exception as e:
        log.error(f"Error processing chat mutation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


@app.get("/api/v1/path/{session_id}", response_model=MasterLearningPath)
def get_path_state(session_id: str):
    """Retrieves the current state of a learning path for a given session."""
    session_state = load_session(session_id)
    if not session_state:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session_state.current_path