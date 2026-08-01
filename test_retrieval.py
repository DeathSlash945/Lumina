"""
Sanity test script for testing Lumina's multi-format curriculum generation.

Usage:
    python3 test_retrieval.py "Data Structures" beginner balanced
    python3 test_retrieval.py "Heaps" expert more_video
"""
import sys
import logging
from retrieval.orchestrator import RetrievalService
from retrieval.schemas import UserExpertise, ContentPreference

# Configure logging to see what Ollama and the search engines are doing
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    # Parse CLI args or fall back to distinct defaults
    topic = sys.argv[1] if len(sys.argv) > 1 else "gradient descent"
    
    level_input = sys.argv[2] if len(sys.argv) > 2 else "beginner"
    pref_input = sys.argv[3] if len(sys.argv) > 3 else "balanced"
    
    # Cast safe schema enums
    try:
        level = UserExpertise(level_input)
        preference = ContentPreference(pref_input)
    except ValueError as e:
        print(f"Error: Invalid arguments passed. Details: {e}")
        print("Available Levels: beginner, intermediate, expert")
        print("Available Preferences: more_text, more_video, balanced")
        sys.exit(1)

    print("\n" + "="*60)
    print(f" LUMINA PATH GENERATION TEST ")
    print("="*60)
    print(f"Topic:       {topic!r}")
    print(f"Skill Tier:  {level.value}")
    print(f"Preference:  {preference.value}")
    print("="*60 + "\n")

    service = RetrievalService()
    
    print("[1/2] Launching generation matrix...")
    path_result = service.generate_custom_path(topic, level, preference)
    
    print("\n" + "="*60)
    print(f" GENERATED CURRICULUM ROADMAP ")
    print("="*60)
    print(f"Main Target: {path_result.main_topic.upper()}")
    print(f"Track Settings: [{path_result.expertise_level.value}] - [{path_result.preference.value}]")
    print("-" * 60)

    for i, step in enumerate(path_result.steps, 1):
        print(f"\nStep {i}: {step.topic_title}")
        print(f"  Estimated Effort: ~{step.estimated_hours} hours")
        print(f"  Resources surfaced ({len(step.resources)}):")
        
        for res in step.resources:
            print(f"    - [{res.resource_type.value.upper()}] ({res.role.value})")
            print(f"      Title: {res.title}")
            print(f"      Link:  {res.url}")
            if res.resource_type.value == "video_segment":
                mins_start, secs_start = divmod(int(res.start_time or 0), 60)
                mins_end, secs_end = divmod(int(res.end_time or 0), 60)
                print(f"      Range: {mins_start}:{secs_start:02d} - {mins_end}:{secs_end:02d}")
            elif res.source_domain:
                print(f"      Host:  {res.source_domain}")
            print(f"      Why:   {res.justification}\n")
            
    print("="*60)

if __name__ == "__main__":
    main()