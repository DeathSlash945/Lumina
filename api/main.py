import json
import sqlite3
from fastapi import FastAPI, HTTPException, status
from retrieval.orchestrator import RetrievalService
from retrieval.schemas import MasterLearningPath, CompletionStatus
from api.schemas import CreatePathRequest, ProgressUpdateRequest

app = FastAPI(
    title="Lumina Curriculum Generation Engine",
    version="1.0.0",
    description="High-performance, dynamic learning path orchestrator"
)

# Global Retrieval Service instance
service = RetrievalService()
DB_PATH = "lumina_sessions.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS roadmaps (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                path_data TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

init_db()

@app.post(
    "/api/v1/curriculum/generate", 
    response_model=MasterLearningPath, 
    status_code=status.HTTP_201_CREATED
)
async def generate_curriculum(payload: CreatePathRequest):
    """Generates a new Master Learning Path or replaces an existing topic path."""
    try:
        roadmap = service.generate_custom_path(
            topic=payload.topic,
            level=payload.expertise_level,
            preference=payload.content_preference
        )
        
        # Save generated path to SQLite
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO roadmaps (id, topic, path_data) VALUES (?, ?, ?)",
                (payload.topic.lower().strip(), payload.topic, roadmap.model_dump_json())
            )
            
        return roadmap
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline generation error: {str(e)}")

@app.get("/api/v1/curriculum/{topic}", response_model=MasterLearningPath)
async def get_curriculum(topic: str):
    """Retrieves a cached learning path from SQLite without re-running search providers."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT path_data FROM roadmaps WHERE id = ?", (topic.lower().strip(),))
        row = cursor.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail=f"No roadmap found for topic '{topic}'.")
        
    return json.loads(row[0])

@app.patch("/api/v1/curriculum/{topic}/progress")
async def update_step_progress(topic: str, payload: ProgressUpdateRequest):
    """Updates progress status for a step and recalculates overall roadmap completion percentage."""
    normalized_id = topic.lower().strip()
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT path_data FROM roadmaps WHERE id = ?", (normalized_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"No roadmap found for topic '{topic}'.")
            
        path_dict = json.loads(row[0])
        steps = path_dict.get("steps", [])
        
        if payload.step_index >= len(steps):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid step_index {payload.step_index}. Total steps: {len(steps)}."
            )
            
        # Update step status
        steps[payload.step_index]["status"] = payload.status
        
        # Compute overall progress percentage
        completed_count = sum(1 for s in steps if s.get("status") == CompletionStatus.COMPLETED.value)
        total_progress = round((completed_count / len(steps)) * 100, 1) if steps else 0.0
        
        # Save updated state
        conn.execute(
            "UPDATE roadmaps SET path_data = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(path_dict), normalized_id)
        )
        
    return {
        "topic": topic,
        "updated_step_index": payload.step_index,
        "step_status": payload.status,
        "total_roadmap_progress_pct": total_progress
    }