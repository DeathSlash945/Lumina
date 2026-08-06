"""
End-to-End System Health Check & Performance Test for Project Lumina
"""
import time
from retrieval.schemas import UserExpertise, ContentPreference, CompletionStatus
from retrieval.progress_tracker import ProgressTracker
from retrieval.db import init_db, save_session, load_session
from retrieval.chat_agent import LuminaChatAgent

import logging

logging.basicConfig(
    filename="lumina.log",
    filemode="a",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

def run_system_check():
    print("="*60)
    print("RUNNING LUMINA SYSTEM INTEGRATION CHECK")
    print("="*60)
    
    # 1. Database Initialization
    init_db()
    print("SQLite Database Initialized.")
    
    # 2. Path Generation Speed & Output
    agent = LuminaChatAgent()
    start_time = time.time()
    
    test_session_id = "test-system-session-999"
    word=input("Enter your topic: ")
    print("\nGenerating path for: ", word)
    
    session = agent.initialize_session(word, UserExpertise.INTERMEDIATE, ContentPreference.BALANCED)
    elapsed = time.time() - start_time
    
    print(f"Path generated in {elapsed:.2f} seconds!")
    
    # 3. Save to Database & Load Back
    save_session(test_session_id, session)
    loaded_session = load_session(test_session_id)
    assert loaded_session is not None, "Failed to load session from SQLite!"
    print("SQLite Persistence Verified (Save & Load).")
    
    # 4. Resource Quality & Rating Verification
    path = loaded_session.current_path
    print(f"\nGenerated Roadmap: {path.main_topic} ({len(path.steps)} Steps)")
    
    for idx, step in enumerate(path.steps, 1):
        print(f"\n  Step {idx + 1}: {step.topic_title} [{step.role.value.upper()}] | Est Effort: {step.estimated_hours} hrs")
        for res in step.resources:
            rating_str = f"Rating: {res.rating}/5.0" if res.rating else "Rating: N/A"
            platform_str = res.source_platform or "Web"
            print(f"    • [{res.resource_type.value.title()}] | {platform_str} | {rating_str} | {res.title}")
            print(f"      URL: {res.url}")
            
    # 5. Progress Tracking Mutation Test
    print("\nTesting Progress Tracking State Transitions...")
    updated_path = ProgressTracker.update_resource_status(
        path, step_idx=0, resource_idx=0, new_status=CompletionStatus.COMPLETED
    )
    print(f"Step 1 Progress: {updated_path.steps[0].progress_percentage}%")
    print(f"Total Roadmap Progress: {updated_path.total_progress}%")

if __name__ == "__main__":
    run_system_check()