"""
State schemas for the Chat Agent supervisor graph.

Defines ChatAgentState TypedDict that flows through the intent classification
and sub-agent routing graph:

    classify_intent → {smart_apply | services | rcic | ask_clarification} → END

The messages field uses Annotated[List, operator.add] so that each node
appends new messages rather than replacing the entire list.
"""

from typing import TypedDict, List, Optional, Dict, Any
from typing_extensions import Annotated
import operator

# Valid intent values that the classifier can produce.
# Used by the conditional edge function after classify_intent.
IntentType = str  # "smart_apply" | "services" | "rcic" | "unclear"


class ChatAgentState(TypedDict, total=False):
    """
    Complete state for the Chat Agent supervisor workflow.

    State flows through nodes:
    classify_intent → call_smart_apply | call_services_stub | call_rcic_stub | ask_clarification

    Fields:
        messages: Conversation history — accumulated via operator.add
        intent: Classified intent from the classify_intent node
        sub_agent_response: Response payload from whichever sub-agent was called
        user_context: Optional context passed from the Go JWT middleware
        error_message: Error description when a sub-agent call fails
        session_id: Unique session identifier for checkpointer
        current_step: Current graph step for observability
        needs_user_input: True when Smart Apply paused awaiting user input (profile question or approval)
        user_response: User's reply to forward as user_response in the Smart Apply request on resume turns
    """

    # Conversation history — each node appends, never replaces
    messages: Annotated[List[Dict[str, Any]], operator.add]

    # Intent classification result
    intent: Optional[IntentType]

    # Raw response from the called sub-agent
    sub_agent_response: Optional[Dict[str, Any]]

    # Context forwarded from Go (user_id, preferences, etc.)
    user_context: Optional[Dict[str, Any]]

    # Error information when things go wrong
    error_message: Optional[str]

    # Classified error type for type-specific user messages.
    # Values: "timeout" | "connection" | "server_error" | "not_found" | "bad_request" | "unknown"
    error_type: Optional[str]

    # Session tracking for MemorySaver checkpointer
    session_id: Optional[str]

    # Observability: which step are we on
    current_step: Optional[str]

    # Multi-turn continuity: True when Smart Apply paused awaiting user input
    # (e.g., profile question or approval). The Chat Agent detects this and
    # relays the question to the user instead of ending the conversation.
    needs_user_input: Optional[bool]

    # Multi-turn continuity: User's reply to the paused question. Forwarded
    # as user_response in the Smart Apply request when resuming the session.
    user_response: Optional[str]
