"""
Chat Agent package — LangGraph supervisor for intent classification and sub-agent routing.

Public API:
    create_chat_agent_graph() → Compiled LangGraph StateGraph
    ChatAgentState            → TypedDict state schema
    SmartApplyClient          → Async HTTP client for Smart Apply sub-agent
    classify_intent           → LLM-based intent classification node
    route_intent              → Conditional edge routing function
    call_smart_apply          → HTTP call to Smart Apply sub-agent
    call_services_stub        → Services sub-agent stub
    call_rcic_stub            → RCIC sub-agent stub
    ask_clarification         → Clarifying question node
    handle_sub_agent_error    → Error handling fallback node
"""

from src.chat_agent.state import ChatAgentState
from src.chat_agent.graph import create_chat_agent_graph
from src.chat_agent.nodes import (
    classify_intent,
    route_intent,
    call_smart_apply,
    call_services_stub,
    call_rcic_stub,
    ask_clarification,
    handle_sub_agent_error,
)
from src.chat_agent.smartapply_client import SmartApplyClient

__all__ = [
    "ChatAgentState",
    "create_chat_agent_graph",
    "classify_intent",
    "route_intent",
    "call_smart_apply",
    "call_services_stub",
    "call_rcic_stub",
    "ask_clarification",
    "handle_sub_agent_error",
    "SmartApplyClient",
]
