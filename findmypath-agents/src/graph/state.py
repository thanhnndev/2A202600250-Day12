"""
State schemas for LangGraph agent workflow.

Defines TypedDict structures for:
- UserProfile: User's preferences and constraints
- SchoolResult: Matched school with scoring
- AgentState: Complete state for the recommendation flow
"""

from typing import TypedDict, List, Optional, Dict, Any
from typing_extensions import Annotated
import operator


class UserProfile(TypedDict, total=False):
    """User profile collected during conversation."""
    name: str
    email: str
    phone: str
    gpa: float
    budget: float  # USD per year
    preferred_countries: List[str]
    major: str
    preferred_city: Optional[str]
    notes: Optional[str]


class SchoolResult(TypedDict):
    """School search result with match scoring."""
    school_id: str
    name: str
    country: str
    city: str
    match_score: float  # 0-100
    reasons: List[str]  # Why this school matches
    programs_count: int


class Message(TypedDict):
    """Single message in conversation history."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: Optional[str]


class AgentState(TypedDict):
    """
    Complete state for the Smart Apply agent workflow.
    
    State flows through nodes:
    Profile Collector → School Finder → Human Approval → Document Generator
    """
    # Conversation history
    messages: Annotated[List[Message], operator.add]
    
    # User information
    user_profile: UserProfile
    
    # Search results
    schools: List[SchoolResult]
    selected_schools: List[SchoolResult]  # Top 3 chosen by user
    
    # Document generation
    pdf_path: Optional[str]
    pdf_generated: bool
    
    # Flow control
    current_step: str
    needs_user_input: bool
    user_feedback: Optional[str]
    
    # Metadata
    session_id: str
    created_at: Optional[str]
    updated_at: Optional[str]
    
    # User context from Go JWT middleware (forwarded through chat_agent graph)
    user_context: Optional[Dict[str, Any]]
