import uuid
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from retrieval.schemas import MasterLearningPath, UserExpertise, ContentPreference
from retrieval.chat_agent import LuminaChatAgent, ChatSessionState

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lumina.api")

app = FastAPI(
    title="Project Lumina Engine",
    description="Automated, personalized learning path generator and stateful curriculum assistant.",
    version="1.0.0"
)

# Enable CORS for local UI development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory session cache (backed by ChatSessionState)
SESSION_STORE: dict[str, ChatSessionState] = {}
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
        SESSION_STORE[session_id] = session_state
        
        initial_msg = session_state.conversation_history[-1]["content"]
        
        return InitSessionResponse(
            session_id=session_id,
            path=session_state.current_path,
            initial_message=initial_msg
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
    if req.session_id not in SESSION_STORE:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
        
    session_state = SESSION_STORE[req.session_id]
    
    try:
        response_text, updated_session = CHAT_AGENT.process_message(
            session=session_state,
            user_message=req.message
        )
        
        # Persist updated session state
        SESSION_STORE[req.session_id] = updated_session
        
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
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SESSION_STORE[session_id].current_path