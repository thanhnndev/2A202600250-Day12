"""
Pytest fixtures for Smart Apply agent tests.

Provides reusable test data, mocks, and utilities for:
- Mock user profiles
- Mock school data
- Mock Go backend responses
- Test state initialization
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List


@pytest.fixture
def mock_user_profile() -> Dict[str, Any]:
    """Provides a complete mock user profile for testing."""
    return {
        "name": "Nguyen Van A",
        "email": "nguyenvana@example.com",
        "phone": "+84 90 123 4567",
        "gpa": 3.7,
        "budget": 35000,
        "preferred_countries": ["USA", "Canada"],
        "major": "Computer Science",
        "preferred_city": None,
        "notes": None
    }


@pytest.fixture
def mock_user_profile_low_gpa() -> Dict[str, Any]:
    """Provides a mock user profile with low GPA for edge case testing."""
    return {
        "name": "Tran Thi B",
        "email": "tranthib@example.com",
        "phone": "+84 91 234 5678",
        "gpa": 2.5,
        "budget": 20000,
        "preferred_countries": ["Vietnam"],
        "major": "Business Administration",
        "preferred_city": "Ho Chi Minh City",
        "notes": "Needs scholarship"
    }


@pytest.fixture
def mock_user_profile_high_budget() -> Dict[str, Any]:
    """Provides a mock user profile with high budget for edge case testing."""
    return {
        "name": "Le Van C",
        "email": "levanc@example.com",
        "phone": "+84 92 345 6789",
        "gpa": 4.0,
        "budget": 100000,
        "preferred_countries": ["USA", "UK", "Australia"],
        "major": "Medicine",
        "preferred_city": None,
        "notes": "Prefers Ivy League"
    }


@pytest.fixture
def mock_schools() -> List[Dict[str, Any]]:
    """Provides a list of mock school data for testing."""
    return [
        {
            "school_id": "sch_001",
            "name": "University of California, Berkeley",
            "country": "USA",
            "city": "Berkeley, CA",
            "match_score": 95.5,
            "reasons": ["Excellent GPA match", "Strong CS program", "Within budget"],
            "programs_count": 150
        },
        {
            "school_id": "sch_002",
            "name": "University of Toronto",
            "country": "Canada",
            "city": "Toronto, ON",
            "match_score": 91.0,
            "reasons": ["Good GPA match", "Affordable tuition", "AI research hub"],
            "programs_count": 120
        },
        {
            "school_id": "sch_003",
            "name": "Carnegie Mellon University",
            "country": "USA",
            "city": "Pittsburgh, PA",
            "match_score": 88.5,
            "reasons": ["Top CS program", "Industry connections", "Scholarship available"],
            "programs_count": 100
        },
        {
            "school_id": "sch_004",
            "name": "Stanford University",
            "country": "USA",
            "city": "Stanford, CA",
            "match_score": 92.3,
            "reasons": ["Top ranking", "Research opportunities", "Silicon Valley location"],
            "programs_count": 200
        },
        {
            "school_id": "sch_005",
            "name": "MIT",
            "country": "USA",
            "city": "Cambridge, MA",
            "match_score": 88.7,
            "reasons": ["Prestigious", "Strong alumni network", "Innovation hub"],
            "programs_count": 180
        }
    ]


@pytest.fixture
def mock_schools_empty() -> List[Dict[str, Any]]:
    """Provides an empty list of schools for edge case testing."""
    return []


@pytest.fixture
def mock_schools_single() -> List[Dict[str, Any]]:
    """Provides a single school for edge case testing."""
    return [
        {
            "school_id": "sch_001",
            "name": "Only University",
            "country": "USA",
            "city": "Single City",
            "match_score": 75.0,
            "reasons": ["Only option available"],
            "programs_count": 50
        }
    ]


@pytest.fixture
def mock_schools_same_score() -> List[Dict[str, Any]]:
    """Provides schools with identical match scores for tie-breaking tests."""
    return [
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
            "match_score": 90.0,
            "reasons": ["Good match"],
            "programs_count": 120
        },
        {
            "school_id": "sch_003",
            "name": "University C",
            "country": "USA",
            "city": "City C",
            "match_score": 90.0,
            "reasons": ["Good match"],
            "programs_count": 80
        }
    ]


@pytest.fixture
def mock_agent_state(mock_user_profile, mock_schools) -> Dict[str, Any]:
    """Provides a complete mock agent state for testing."""
    return {
        "messages": [
            {"role": "user", "content": "I want to study Computer Science", "timestamp": None},
            {"role": "assistant", "content": "I'll help you find schools", "timestamp": None}
        ],
        "user_profile": mock_user_profile,
        "schools": mock_schools,
        "selected_schools": [],
        "pdf_path": None,
        "pdf_generated": False,
        "current_step": "schools_found",
        "needs_user_input": False,
        "user_feedback": None,
        "session_id": "test_session_123",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": None
    }


@pytest.fixture
def mock_agent_state_empty_schools(mock_user_profile) -> Dict[str, Any]:
    """Provides agent state with no schools found."""
    return {
        "messages": [],
        "user_profile": mock_user_profile,
        "schools": [],
        "selected_schools": [],
        "pdf_path": None,
        "pdf_generated": False,
        "current_step": "schools_not_found",
        "needs_user_input": True,
        "user_feedback": None,
        "session_id": "test_session_empty",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": None
    }


@pytest.fixture
def mock_go_backend_response() -> Dict[str, Any]:
    """Provides a mock Go backend API response."""
    return {
        "status": "success",
        "data": {
            "countries": [
                {"country_id": "1", "name": "USA", "code": "US"},
                {"country_id": "2", "name": "Canada", "code": "CA"},
                {"country_id": "3", "name": "Australia", "code": "AU"}
            ],
            "schools": [
                {
                    "school_id": "1",
                    "name": "Test University",
                    "country": "USA",
                    "city": "Test City",
                    "category": "Public",
                    "match_score": 85.0,
                    "programs_count": 100
                }
            ]
        }
    }


@pytest.fixture
def mock_go_backend_error() -> Dict[str, Any]:
    """Provides a mock Go backend error response."""
    return {
        "status": "error",
        "error": {
            "code": 500,
            "message": "Internal server error"
        }
    }


@pytest.fixture
def temp_output_dir(tmp_path):
    """Provides a temporary directory for output files."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def approval_test_cases():
    """Provides test cases for human approval routing."""
    return [
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
    ]


# ── Chat Agent (supervisor graph) fixtures ──────────────────────────────────

@pytest.fixture
def chat_agent_graph():
    """Provides a compiled ChatAgentStateGraph for testing."""
    from src.chat_agent.graph import create_chat_agent_graph
    return create_chat_agent_graph()


@pytest.fixture
def chat_state_basic():
    """Provides a minimal ChatAgentState for testing."""
    return {
        "messages": [{"role": "user", "content": "I want to find schools"}],
        "intent": None,
        "sub_agent_response": None,
        "user_context": {"user_id": "test-user-1"},
        "error_message": None,
        "session_id": "test-session-1",
        "current_step": "start",
    }


@pytest.fixture
def chat_state_services():
    """ChatAgentState with a services-intent message."""
    return {
        "messages": [{"role": "user", "content": "what services do you offer?"}],
        "intent": None,
        "sub_agent_response": None,
        "user_context": None,
        "error_message": None,
        "session_id": "test-session-2",
        "current_step": "start",
    }


@pytest.fixture
def chat_state_rcic():
    """ChatAgentState with an RCIC-intent message."""
    return {
        "messages": [{"role": "user", "content": "help me with my study permit"}],
        "intent": None,
        "sub_agent_response": None,
        "user_context": None,
        "error_message": None,
        "session_id": "test-session-3",
        "current_step": "start",
    }


@pytest.fixture
def chat_state_unclear():
    """ChatAgentState with an unclear-intent message."""
    return {
        "messages": [{"role": "user", "content": "hello there"}],
        "intent": None,
        "sub_agent_response": None,
        "user_context": None,
        "error_message": None,
        "session_id": "test-session-4",
        "current_step": "start",
    }


@pytest.fixture
def chat_intent_routing_cases():
    """Test cases for intent → route mapping."""
    return [
        ("smart_apply", "call_smart_apply"),
        ("services", "call_services_stub"),
        ("rcic", "call_rcic_stub"),
        ("unclear", "ask_clarification"),
        ("invalid_intent", "ask_clarification"),  # fallback
    ]


@pytest.fixture
def keyword_classification_cases():
    """Test cases for keyword-based intent classification."""
    return [
        # smart_apply
        ("I want to find schools in Canada", "smart_apply"),
        ("apply to university program", "smart_apply"),
        ("college recommendation", "smart_apply"),
        # rcic
        ("help me with visa application", "rcic"),
        ("immigration advice needed", "rcic"),
        ("RCIC consultation", "rcic"),
        ("permanent residency requirements", "rcic"),
        ("citizenship test prep", "rcic"),
        ("PR application help", "rcic"),
        # services
        ("what services are available", "services"),
        # unclear
        ("hello", "unclear"),
        ("thanks", "unclear"),
        ("random gibberish xyz", "unclear"),
    ]
