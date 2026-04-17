"""
Test Human Approval node specifically.

Tests the human_approval node with mock data to verify:
1. Top 3 schools are selected correctly
2. Approval message is formatted properly
3. Routing logic works for yes/no responses
4. Edge cases: empty schools, single school, tie scores

Run with: pytest tests/test_human_approval.py -v
       or: python tests/test_human_approval.py
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any, List

import pytest

# Add src to path
src_path = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, src_path)

from src.graph.nodes import human_approval, route_human_approval
from src.graph.state import AgentState, SchoolResult


class TestHumanApprovalNode:
    """Test the human_approval node with various scenarios."""
    
    def test_human_approval_selects_top_3(self, mock_schools, mock_user_profile):
        """Test that human_approval correctly selects top 3 schools from 5."""
        print("\n" + "=" * 60)
        print("🧪 Testing Human Approval Node - Top 3 Selection")
        print("=" * 60)
        
        # Create mock state
        mock_state: AgentState = {
            "messages": [],
            "user_profile": mock_user_profile,
            "schools": mock_schools,
            "selected_schools": [],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "schools_found",
            "needs_user_input": False,
            "user_feedback": None,
            "session_id": "test_001",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        print(f"📋 Input: {len(mock_schools)} schools with scores: " +
              ", ".join(f"{s['match_score']}" for s in mock_schools))
        
        # Execute node
        result = human_approval(mock_state)
        
        # Verify results
        print("\n✅ Output Verification:")
        print("-" * 60)
        
        # Check selected_schools
        selected = result.get("selected_schools", [])
        assert len(selected) == 3, f"Expected 3 schools, got {len(selected)}"
        print(f"✓ Selected 3 schools (top 3 from {len(mock_schools)})")
        
        # Verify top 3 are the highest scoring
        expected_top3_names = [
            "University of California, Berkeley",  # 95.5
            "Stanford University",  # 92.3
            "University of Toronto"  # 91.0
        ]
        actual_top3_names = [s["name"] for s in selected]
        assert actual_top3_names == expected_top3_names, \
            f"Expected {expected_top3_names}, got {actual_top3_names}"
        print(f"✓ Correct top 3 schools selected by match score")
        
        # Check current_step
        assert result.get("current_step") == "awaiting_approval", \
            f"Expected 'awaiting_approval', got {result.get('current_step')}"
        print(f"✓ Current step set to 'awaiting_approval'")
        
        # Check needs_user_input
        assert result.get("needs_user_input") == True, \
            "Expected needs_user_input=True"
        print(f"✓ needs_user_input flag set to True")
        
        # Check interrupt_reason
        assert result.get("interrupt_reason") == "human_approval_required", \
            "Expected interrupt_reason='human_approval_required'"
        print(f"✓ interrupt_reason set correctly")
        
        # Check message formatting
        messages = result.get("messages", [])
        assert len(messages) > 0, "Expected at least one message"
        approval_msg = messages[-1]
        assert approval_msg["role"] == "assistant", "Expected assistant message"
        print(f"✓ Approval message created")
        
        # Display the formatted message
        print("\n📄 Formatted Approval Message Preview:")
        print("-" * 60)
        content_preview = approval_msg["content"][:200] + "..."
        print(content_preview)
        
        return True
    
    def test_human_approval_empty_schools(self, mock_user_profile):
        """Test human_approval with empty schools list (edge case)."""
        print("\n🧪 Edge Case: Empty schools list")
        
        mock_state: AgentState = {
            "messages": [],
            "user_profile": mock_user_profile,
            "schools": [],
            "selected_schools": [],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "schools_not_found",
            "needs_user_input": False,
            "user_feedback": None,
            "session_id": "test_empty",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        result = human_approval(mock_state)
        
        # Should handle gracefully with empty selection
        selected = result.get("selected_schools", [])
        assert len(selected) == 0, "Should select 0 schools from empty list"
        print("✅ Empty schools list handled correctly")
        
        return True
    
    def test_human_approval_single_school(self, mock_schools_single, mock_user_profile):
        """Test human_approval with single school (edge case)."""
        print("\n🧪 Edge Case: Single school")
        
        mock_state: AgentState = {
            "messages": [],
            "user_profile": mock_user_profile,
            "schools": mock_schools_single,
            "selected_schools": [],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "schools_found",
            "needs_user_input": False,
            "user_feedback": None,
            "session_id": "test_single",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        result = human_approval(mock_state)
        
        # Should select the single school
        selected = result.get("selected_schools", [])
        assert len(selected) == 1, f"Should select 1 school, got {len(selected)}"
        print("✅ Single school handled correctly")
        
        return True
    
    def test_human_approval_two_schools(self, mock_user_profile):
        """Test human_approval with exactly 2 schools (edge case)."""
        print("\n🧪 Edge Case: Two schools")
        
        two_schools = [
            {
                "school_id": "sch_001",
                "name": "University A",
                "country": "USA",
                "city": "City A",
                "match_score": 90.0,
                "reasons": ["Good match"],
                "programs_count": 100
            },
            {
                "school_id": "sch_002",
                "name": "University B",
                "country": "USA",
                "city": "City B",
                "match_score": 85.0,
                "reasons": ["Good match"],
                "programs_count": 80
            }
        ]
        
        mock_state: AgentState = {
            "messages": [],
            "user_profile": mock_user_profile,
            "schools": two_schools,
            "selected_schools": [],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "schools_found",
            "needs_user_input": False,
            "user_feedback": None,
            "session_id": "test_two",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        result = human_approval(mock_state)
        
        # Should select both schools (less than 3)
        selected = result.get("selected_schools", [])
        assert len(selected) == 2, f"Should select 2 schools, got {len(selected)}"
        print("✅ Two schools handled correctly")
        
        return True
    
    def test_human_approval_tie_scores(self, mock_schools_same_score, mock_user_profile):
        """Test human_approval with schools having identical scores (edge case)."""
        print("\n🧪 Edge Case: Schools with identical match scores")
        
        mock_state: AgentState = {
            "messages": [],
            "user_profile": mock_user_profile,
            "schools": mock_schools_same_score,
            "selected_schools": [],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "schools_found",
            "needs_user_input": False,
            "user_feedback": None,
            "session_id": "test_tie",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        result = human_approval(mock_state)
        
        # Should still select top 3 (even with ties)
        selected = result.get("selected_schools", [])
        assert len(selected) == 3, f"Should select 3 schools, got {len(selected)}"
        print("✅ Tie scores handled correctly")
        
        return True
    
    def test_human_approval_message_format(self, mock_schools, mock_user_profile):
        """Test that approval message contains required information."""
        print("\n🧪 Testing approval message format")
        
        mock_state: AgentState = {
            "messages": [],
            "user_profile": mock_user_profile,
            "schools": mock_schools,
            "selected_schools": [],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "schools_found",
            "needs_user_input": False,
            "user_feedback": None,
            "session_id": "test_format",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        result = human_approval(mock_state)
        messages = result.get("messages", [])
        approval_msg = messages[-1]
        content = approval_msg["content"]
        
        # Check for required elements
        assert "3 trường" in content or "3 schools" in content or "3" in content, \
            "Message should mention 3 schools"
        assert "đồng ý" in content.lower() or "yes" in content.lower() or "approve" in content.lower(), \
            "Message should have approval instructions"
        assert "no" in content.lower() or "không" in content.lower() or "tìm lại" in content.lower(), \
            "Message should have rejection instructions"
        
        print("✅ Approval message contains all required elements")
        return True


class TestRouteHumanApproval:
    """Test the routing logic after human approval."""
    
    @pytest.mark.parametrize("user_input,expected_route,description", [
        # Approval cases
        ("yes", "document_generator", "English 'yes'"),
        ("YES", "document_generator", "English 'YES' uppercase"),
        ("Yes", "document_generator", "English 'Yes' mixed case"),
        ("y", "document_generator", "English 'y'"),
        ("Y", "document_generator", "English 'Y' uppercase"),
        ("đồng ý", "document_generator", "Vietnamese 'đồng ý'"),
        ("ĐỒNG Ý", "document_generator", "Vietnamese uppercase"),
        ("ok", "document_generator", "English 'ok'"),
        ("OK", "document_generator", "English 'OK' uppercase"),
        ("okay", "document_generator", "English 'okay'"),
        ("tốt", "document_generator", "Vietnamese 'tốt'"),
        ("good", "document_generator", "English 'good'"),
        ("chấp nhận", "document_generator", "Vietnamese 'chấp nhận'"),
        ("approve", "document_generator", "English 'approve'"),
        # Rejection cases
        ("no", "school_finder", "English 'no'"),
        ("NO", "school_finder", "English 'NO' uppercase"),
        ("No", "school_finder", "English 'No' mixed case"),
        ("n", "school_finder", "English 'n'"),
        ("N", "school_finder", "English 'N' uppercase"),
        ("không", "school_finder", "Vietnamese 'không'"),
        ("KHÔNG", "school_finder", "Vietnamese uppercase"),
        ("nope", "school_finder", "English 'nope'"),
        ("reject", "school_finder", "English 'reject'"),
        ("từ chối", "school_finder", "Vietnamese 'từ chối'"),
        ("tìm lại", "school_finder", "Vietnamese 'tìm lại'"),
        # Edge cases - should default to document_generator
        ("", "document_generator", "Empty string (default)"),
        ("maybe", "document_generator", "Unclear response (default)"),
        ("123", "document_generator", "Numbers (default)"),
        ("!@#$%", "document_generator", "Special chars (default)"),
    ])
    def test_route_human_approval_comprehensive(self, mock_schools, mock_user_profile, 
                                                 user_input, expected_route, description):
        """Test routing with comprehensive set of user inputs."""
        print(f"\n  Testing: {description}")
        
        test_state: AgentState = {
            "messages": [],
            "user_profile": mock_user_profile,
            "schools": mock_schools,
            "selected_schools": mock_schools[:3],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "awaiting_approval",
            "needs_user_input": True,
            "user_feedback": user_input,
            "session_id": "test_route",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        actual_route = route_human_approval(test_state)
        
        assert actual_route == expected_route, \
            f"Input '{user_input}' ({description}) → {actual_route} (expected {expected_route})"
        
        return True
    
    def test_route_human_approval_case_insensitive(self, mock_schools, mock_user_profile):
        """Test that routing is case-insensitive."""
        print("\n🧪 Testing case insensitivity")
        
        test_cases = [
            ("YES", "document_generator"),
            ("Yes", "document_generator"),
            ("yes", "document_generator"),
            ("NO", "school_finder"),
            ("No", "school_finder"),
            ("no", "school_finder"),
        ]
        
        for user_input, expected_route in test_cases:
            test_state: AgentState = {
                "messages": [],
                "user_profile": mock_user_profile,
                "schools": mock_schools,
                "selected_schools": mock_schools[:3],
                "pdf_path": None,
                "pdf_generated": False,
                "current_step": "awaiting_approval",
                "needs_user_input": True,
                "user_feedback": user_input,
                "session_id": "test_case",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": None
            }
            
            actual_route = route_human_approval(test_state)
            assert actual_route == expected_route, \
                f"Input '{user_input}' should route to {expected_route}, got {actual_route}"
        
        print("✅ Case insensitivity works correctly")
        return True
    
    def test_route_human_approval_whitespace(self, mock_schools, mock_user_profile):
        """Test that routing handles whitespace correctly."""
        print("\n🧪 Testing whitespace handling")
        
        test_cases = [
            ("  yes  ", "document_generator"),
            ("\tyes\n", "document_generator"),
            ("  no  ", "school_finder"),
            ("\tno\n", "school_finder"),
        ]
        
        for user_input, expected_route in test_cases:
            test_state: AgentState = {
                "messages": [],
                "user_profile": mock_user_profile,
                "schools": mock_schools,
                "selected_schools": mock_schools[:3],
                "pdf_path": None,
                "pdf_generated": False,
                "current_step": "awaiting_approval",
                "needs_user_input": True,
                "user_feedback": user_input,
                "session_id": "test_whitespace",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": None
            }
            
            actual_route = route_human_approval(test_state)
            assert actual_route == expected_route, \
                f"Input '{repr(user_input)}' should route to {expected_route}, got {actual_route}"
        
        print("✅ Whitespace handling works correctly")
        return True
    
    def test_route_human_approval_default_behavior(self, mock_schools, mock_user_profile):
        """Test that unclear responses default to document_generator."""
        print("\n🧪 Testing default routing for unclear responses")
        
        # Note: "unsure" contains "sure" which could match, so we use truly unclear inputs
        unclear_inputs = ["maybe", "123", "!@#", "whatever", ""]
        
        for user_input in unclear_inputs:
            test_state: AgentState = {
                "messages": [],
                "user_profile": mock_user_profile,
                "schools": mock_schools,
                "selected_schools": mock_schools[:3],
                "pdf_path": None,
                "pdf_generated": False,
                "current_step": "awaiting_approval",
                "needs_user_input": True,
                "user_feedback": user_input,
                "session_id": "test_default",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": None
            }
            
            actual_route = route_human_approval(test_state)
            assert actual_route == "document_generator", \
                f"Unclear input '{user_input}' should default to document_generator, got {actual_route}"
        
        print("✅ Default routing works correctly")
        return True
    
    def test_route_human_approval_none_feedback(self, mock_schools, mock_user_profile):
        """Test routing when user_feedback is None (edge case)."""
        print("\n🧪 Edge Case: None user_feedback")
        
        test_state: AgentState = {
            "messages": [],
            "user_profile": mock_user_profile,
            "schools": mock_schools,
            "selected_schools": mock_schools[:3],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "awaiting_approval",
            "needs_user_input": True,
            "user_feedback": None,
            "session_id": "test_none",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        # Should handle None gracefully (default to document_generator)
        actual_route = route_human_approval(test_state)
        assert actual_route == "document_generator", \
            f"None feedback should default to document_generator, got {actual_route}"
        
        print("✅ None feedback handled correctly")
        return True


def main():
    """Run all human approval tests (for standalone execution)."""
    print("\n" + "=" * 70)
    print("🧪 Smart Apply Agents - Human Approval Test Suite")
    print("=" * 70)
    print(f"⏰ Started at: {datetime.utcnow().isoformat()}")
    
    # Run via pytest if available
    try:
        import pytest
        exit_code = pytest.main([__file__, "-v"])
        return exit_code == 0
    except ImportError:
        print("pytest not available, running tests manually...")
        
        # Create mock data
        mock_schools = [
            {"school_id": "1", "name": "UC Berkeley", "country": "USA", "city": "Berkeley",
             "match_score": 95.5, "reasons": ["Good"], "programs_count": 150},
            {"school_id": "2", "name": "Stanford", "country": "USA", "city": "Stanford",
             "match_score": 92.3, "reasons": ["Good"], "programs_count": 200},
            {"school_id": "3", "name": "CMU", "country": "USA", "city": "Pittsburgh",
             "match_score": 90.1, "reasons": ["Good"], "programs_count": 120},
        ]
        
        mock_user_profile = {
            "name": "Test User",
            "email": "test@example.com",
            "gpa": 3.8,
            "budget": 50000,
            "preferred_countries": ["USA"],
            "major": "Computer Science"
        }
        
        results = {
            "top_3_selection": TestHumanApprovalNode().test_human_approval_selects_top_3(mock_schools, mock_user_profile),
            "routing_basic": TestRouteHumanApproval().test_route_human_approval_case_insensitive(mock_schools, mock_user_profile),
        }
        
        print("\n" + "=" * 70)
        print("📊 Final Results")
        print("=" * 70)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} - {test_name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        print(f"⏰ Completed at: {datetime.utcnow().isoformat()}")
        
        return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
