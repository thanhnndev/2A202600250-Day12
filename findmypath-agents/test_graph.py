"""
CLI test script for LangGraph agent.

Tests the complete flow:
User input → Profile collection → School search → PDF generation
"""

import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

from src.graph.graph import run_agent


def test_complete_flow():
    """Test the complete agent flow with sample input."""
    print("=" * 60)
    print("🎓 Smart Apply Agent - CLI Test")
    print("=" * 60)
    print()
    
    # Sample user input
    user_input = "Tôi muốn tư vấn du học Mỹ"
    
    print(f"👤 User: {user_input}")
    print()
    print("🤖 Agent đang xử lý...\n")
    
    # Run agent
    try:
        final_state = run_agent(user_input, session_id="test_001")
        
        # Display results
        print("\n" + "=" * 60)
        print("📊 Final State Summary")
        print("=" * 60)
        print(f"Current Step: {final_state.get('current_step')}")
        print(f"Profile Complete: {bool(final_state.get('user_profile'))}")
        print(f"Schools Found: {len(final_state.get('schools', []))}")
        print(f"PDF Generated: {final_state.get('pdf_generated')}")
        print()
        
        # Display conversation
        print("💬 Conversation History:")
        print("-" * 60)
        for msg in final_state.get("messages", []):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            emoji = "👤" if role == "user" else "🤖"
            print(f"{emoji} {role}: {content[:200]}...")
        print()
        
        # Display selected schools
        if final_state.get("selected_schools"):
            print("🏫 Selected Schools:")
            print("-" * 60)
            for i, school in enumerate(final_state["selected_schools"], 1):
                print(f"{i}. {school['name']} (Score: {school['match_score']})")
            print()
        
        print("✅ Test PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Test FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_complete_flow()
    exit(0 if success else 1)
