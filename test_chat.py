"""
Interactive test runner for Project Lumina stateful curriculum updates & resource link rendering.
"""
import sys
from retrieval.chat_agent import LuminaChatAgent
from retrieval.schemas import UserExpertise, ContentPreference

def print_path_details(path):
    """Prints step details along with exact resource links and timestamp ranges."""
    print("\n" + "="*60)
    print(f"LUMINA ROADMAP METRICS & DEEP LINKS ({path.main_topic})")
    print("="*60)
    
    for i, step in enumerate(path.steps, 1):
        print(f"\nStep {i}: {step.topic_title}")
        print(f"  Estimated Effort: ~{step.estimated_hours} hours ({len(step.resources)} items)")
        
        if not step.resources:
            print("  (No resources surfaced)")
            continue
            
        for res in step.resources:
            r_type = res.resource_type.value if hasattr(res.resource_type, 'value') else str(res.resource_type)
            r_role = res.role.value if hasattr(res.role, 'value') else str(res.role)
            
            if r_type == "VIDEO_SEGMENT" and res.start_time is not None:
                start_m, start_s = divmod(int(res.start_time), 60)
                end_m, end_s = divmod(int(res.end_time), 60)
                print(f" > [{r_type}] ({r_role}) {res.title}")
                print(f"    Link:  {res.url}")
                print(f"    Range: {start_m}:{start_s:02d} - {end_m}:{end_s:02d}")
            else:
                print(f" > [{r_type}] ({r_role}) {res.title}")
                print(f"    Link:  {res.url}")

def interactive_loop():
    print("="*60)
    print(" LUMINA STATEFUL INTERACTIVE CHAT RUNNER ")
    print("="*60)
    
    agent = LuminaChatAgent()
    word= input("The topic you wanna learn: ")
    
    print("[System] Initializing path for ", word)
    session = agent.initialize_session(word, UserExpertise.BEGINNER, ContentPreference.BALANCED)
    
    print(f"\n[Lumina]: {session.conversation_history[-1]['content']}")
    
    # Print initial resources and links
    print_path_details(session.current_path)
    
    while True:
        try:
            user_in = input("\n[User]: ").strip()
            if user_in.lower() in ["exit", "quit"]:
                print("Ending session.")
                break
                
            if not user_in:
                continue
                
            response, session = agent.process_message(session, user_in)
            print(f"\n[Lumina]: {response}")
            
            # Print updated schedule metrics and updated links after each mutation
            print_path_details(session.current_path)
                
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    interactive_loop()