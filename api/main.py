import os
from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import CreatePathRequest, ProgressUpdateRequest
from retrieval.schemas import MasterLearningPath, CompletionStatus
from retrieval.orchestrator import RetrievalService

from urllib.parse import unquote

app = FastAPI(title="Lumina Curriculum Engine")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = RetrievalService()

@app.post(
    "/api/v1/curriculum/generate",
    response_model=MasterLearningPath,
    status_code=status.HTTP_201_CREATED
)
def generate_curriculum(payload: CreatePathRequest):
    try:
        path = service.generate_custom_path(
            topic=payload.topic,
            level=payload.expertise_level,
            preference=payload.content_preference,
            groq_api_key=payload.groq_api_key
        )
        return path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/v1/curriculum/{topic}/progress")
def update_progress(topic: str, payload: ProgressUpdateRequest):
    topic = unquote(topic).strip().lower()
    success = service.update_step_status(topic, payload.step_index, payload.status)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Topic '{topic}' or step index {payload.step_index} not found."
        )
    return {"status": "updated", "topic": topic, "step_index": payload.step_index, "new_status": payload.status}

# Mount static frontend files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")