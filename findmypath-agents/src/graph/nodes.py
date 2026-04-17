"""
LangGraph node implementations for Smart Apply agent.

Nodes:
- profile_collector: Gather user information through questions
- school_finder: Search and rank schools based on profile
- human_approval: Get user confirmation on selected schools using LangGraph interrupts
- document_generator: Create PDF recommendation document
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Literal
from src.graph.state import AgentState, UserProfile, SchoolResult, Message

logger = logging.getLogger(__name__)


def profile_collector(state: AgentState) -> Dict[str, Any]:
    """
    Profile Collector Node
    
    Asks user questions to gather:
    - Name, email, phone
    - GPA, budget
    - Preferred countries, major
    - Any special requirements
    
    When user_context is present (from JWT), pre-populates known fields
    and skips asking for them.
    
    Returns updated state with collected profile info.
    """
    messages = state.get("messages", [])
    user_profile = state.get("user_profile", {})
    user_context = state.get("user_context") or {}
    
    # Define required fields and questions
    required_fields = {
        "name": "Bạn tên gì?",
        "email": "Email của bạn là gì?",
        "gpa": "GPA hiện tại của bạn? (thang 4.0)",
        "budget": "Ngân sách dự kiến mỗi năm? (USD)",
        "preferred_countries": "Bạn muốn du học ở nước nào? (ví dụ: USA, Canada, Australia)",
        "major": "Bạn muốn học ngành gì?"
    }
    
    # Pre-populate user_profile from user_context
    prepopulated_fields = []
    prepop_map = {
        "email": "email",
        "name": "name",
    }
    for profile_field, context_field in prepop_map.items():
        value = user_context.get(context_field)
        if value and not user_profile.get(profile_field):
            user_profile[profile_field] = value
            prepopulated_fields.append(profile_field)
    
    # Log pre-population status (only user_id for privacy)
    if prepopulated_fields:
        user_id = user_context.get("user_id", "unknown")
        logger.info(
            f"profile_collector: pre-populated fields {prepopulated_fields} "
            f"from user_context for user_id={user_id}"
        )
    else:
        logger.info("profile_collector: no pre-populated fields from user_context")
    
    # Check what's missing (after pre-population)
    missing_fields = [
        field for field, question in required_fields.items()
        if field not in user_profile or not user_profile[field]
    ]
    
    if not missing_fields:
        # Profile complete, return as-is
        return {"user_profile": user_profile, "current_step": "profile_complete"}
    
    # Generate question for next missing field
    next_field = missing_fields[0]
    question = required_fields[next_field]
    
    # Add question to messages
    assistant_message = Message(
        role="assistant",
        content=f"📋 {question}",
        timestamp=datetime.utcnow().isoformat()
    )
    
    return {
        "user_profile": user_profile,
        "messages": [assistant_message],
        "needs_user_input": True,
        "current_step": "collecting_profile"
    }


def school_finder(state: AgentState) -> Dict[str, Any]:
    """
    School Finder Node
    
    Searches for schools matching user profile:
    - Filter by country, budget, major
    - Rank by GPA match, affordability
    - Return top 5-10 schools
    
    Returns updated state with search results.
    """
    from src.tools.school_tools import tool_search_schools
    
    user_profile = state.get("user_profile", {})
    
    # Extract search criteria
    preferred_countries = user_profile.get("preferred_countries", [])
    gpa = user_profile.get("gpa")
    budget = user_profile.get("budget")
    
    # Call real API tool
    try:
        schools_data = tool_search_schools(
            country_name=preferred_countries[0] if preferred_countries else None,
            gpa=gpa,
            budget=budget
        )
    except Exception as e:
        logger.error(f"School finder error: {e}")
        schools_data = []
    
    if not schools_data:
        # Fallback message if no schools found
        assistant_message = Message(
            role="assistant",
            content="⚠️ Hiện tại chưa có trường nào trong hệ thống. Vui lòng thử lại sau.",
            timestamp=datetime.utcnow().isoformat()
        )
        return {
            "messages": [assistant_message],
            "schools": [],
            "current_step": "schools_not_found"
        }
    
    # Convert to SchoolResult format
    schools: List[SchoolResult] = []
    for s in schools_data[:10]:  # Limit to top 10
        schools.append({
            "school_id": s.get("school_id"),
            "name": s.get("name"),
            "country": s.get("country"),
            "city": s.get("city"),
            "match_score": s.get("match_score", 70.0),
            "reasons": s.get("reasons", ["School found"]),
            "programs_count": s.get("programs_count", 0)
        })
    
    # Add search results to messages
    schools_summary = "\n".join([
        f"  {i+1}. {s['name']} (Score: {s['match_score']:.1f}) - {', '.join(s['reasons'][:2])}"
        for i, s in enumerate(schools[:5])
    ])
    
    assistant_message = Message(
        role="assistant",
        content=f"🎓 Tìm thấy {len(schools)} trường phù hợp:\n\n{schools_summary}\n\nĐang chọn 3 trường tốt nhất...",
        timestamp=datetime.utcnow().isoformat()
    )
    
    return {
        "messages": [assistant_message],
        "schools": schools,
        "current_step": "schools_found"
    }


def human_approval(state: AgentState) -> Dict[str, Any]:
    """
    Human Approval Node
    
    Shows top 3 schools to user and asks for confirmation using LangGraph interrupt.
    This node will pause execution and wait for human input before continuing.
    
    Returns updated state with approval status.
    """
    schools = state.get("schools", [])
    
    # Select top 3 schools
    selected = sorted(schools, key=lambda x: x["match_score"], reverse=True)[:3]
    
    # Format schools for display
    schools_display = "\n".join([
        f"  {i+1}. 🎓 {s['name']}\n"
        f"     📍 {s['city']}, {s['country']}\n"
        f"     ⭐ Match Score: {s['match_score']:.1f}%\n"
        f"     📌 Lý do: {', '.join(s['reasons'][:2])}"
        for i, s in enumerate(selected)
    ])
    
    # Create approval request message
    approval_message = Message(
        role="assistant",
        content=(
            f"✅ Đã tìm thấy 3 trường phù hợp nhất với bạn:\n\n"
            f"{schools_display}\n\n"
            f"❓ Bạn có đồng ý với danh sách này không?\n"
            f"   • Gõ 'yes' hoặc 'y' để chấp nhận và tạo PDF\n"
            f"   • Gõ 'no' hoặc 'n' để tìm lại trường khác"
        ),
        timestamp=datetime.utcnow().isoformat()
    )
    
    logger.info(f"Human approval: displaying {len(selected)} schools for user confirmation")
    
    # Store selected schools and set state for interrupt
    return {
        "selected_schools": selected,
        "messages": [approval_message],
        "current_step": "awaiting_approval",
        "needs_user_input": True,
        "interrupt_reason": "human_approval_required"
    }


def document_generator(state: AgentState) -> Dict[str, Any]:
    """
    Document Generator Node
    
    Creates PDF recommendation document with:
    - User profile summary
    - Top 3 schools with details
    - Programs and requirements
    - QR code for application
    
    Returns updated state with PDF path.
    """
    from src.tools.document_tools import generate_recommendation_pdf
    
    user_profile = state.get("user_profile", {})
    selected_schools = state.get("selected_schools", [])
    
    # Generate PDF with real data
    try:
        pdf_path = generate_recommendation_pdf(
            user_profile=user_profile,
            schools=selected_schools
        )
    except Exception as e:
        logger.error(f"Document generator error: {e}")
        pdf_path = None
    
    if not pdf_path:
        assistant_message = Message(
            role="assistant",
            content="⚠️ Không thể tạo tài liệu PDF. Vui lòng thử lại sau.",
            timestamp=datetime.utcnow().isoformat()
        )
        return {
            "messages": [assistant_message],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "generation_failed"
        }
    
    assistant_message = Message(
        role="assistant",
        content=f"📄 Đã tạo tài liệu recommendation thành công!\n\n"
                f"📁 File: {os.path.basename(pdf_path)}\n"
                f"📧 Tài liệu đã được gửi về email: {user_profile.get('email', 'N/A')}\n\n"
                f"🎯 Bạn có thể bắt đầu nộp hồ sơ bằng cách truy cập PathCan portal.",
        timestamp=datetime.utcnow().isoformat()
    )
    
    return {
        "messages": [assistant_message],
        "pdf_path": pdf_path,
        "pdf_generated": True,
        "current_step": "complete"
    }


def route_human_approval(state: AgentState) -> Literal["document_generator", "school_finder"]:
    """
    Route after human approval based on user response.
    
    This function is called after the human_approval interrupt is resolved.
    It checks the user's approval response and routes accordingly.
    
    Args:
        state: Current agent state including user_feedback
        
    Returns:
        Next node name based on user response
    """
    # Check both user_feedback and user_approval_response for compatibility
    user_response = state.get("user_feedback", "") or state.get("user_approval_response", "")
    user_response = user_response.lower().strip()
    
    # Approval keywords
    approval_keywords = ["yes", "y", "đồng ý", "ok", "okay", "tốt", "good", "chấp nhận", "approve"]
    # Rejection keywords
    rejection_keywords = ["no", "n", "không", "nope", "reject", "từ chối", "tìm lại"]
    
    # Check for approval
    if any(keyword in user_response for keyword in approval_keywords):
        logger.info("User approved selected schools → routing to document_generator")
        return "document_generator"
    # Check for rejection
    elif any(keyword in user_response for keyword in rejection_keywords):
        logger.info("User declined selected schools → routing back to school_finder")
        return "school_finder"
    else:
        # Default to approval if unclear response
        logger.warning(f"Unclear user response '{user_response}' → defaulting to document_generator")
        return "document_generator"


def route_after_profile_collection(state: AgentState) -> Literal["continue", "ask_question"]:
    """
    Route after profile collection based on whether profile is complete.
    
    Args:
        state: Current agent state
        
    Returns:
        "continue" if profile is complete, "ask_question" if more info needed
    """
    current_step = state.get("current_step", "")
    
    if current_step == "profile_complete":
        return "continue"
    else:
        # Profile incomplete, need to ask more questions
        return "ask_question"


def should_continue(state: AgentState) -> str:
    """
    Conditional edge function.
    
    Determines next node based on state:
    - If profile incomplete → profile_collector
    - If schools not found → school_finder
    - If schools found → human_approval (with interrupt)
    - After approval → document_generator or school_finder based on response
    """
    current_step = state.get("current_step", "")
    
    if current_step == "collecting_profile":
        return "profile_collector"
    elif current_step == "profile_complete":
        return "school_finder"
    elif current_step == "schools_found":
        return "human_approval"
    elif current_step == "re_searching":
        return "school_finder"
    elif current_step == "complete":
        return "__end__"
    
    return "profile_collector"
