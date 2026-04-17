"""
Node implementations for the Chat Agent supervisor graph.

Eight nodes that power intent classification, sub-agent routing, and
error handling:

1. classify_intent — LLM-based classification with keyword fallback
2. route_intent    — conditional edge function
3. call_smart_apply — HTTP call to Smart Apply sub-agent
4. relay_question — relay Smart Apply interrupt question to user
5. call_services_stub — stub for Services sub-agent (coming soon)
6. call_rcic_stub — stub for RCIC sub-agent (coming soon)
7. ask_clarification — helpful clarifying question
8. handle_sub_agent_error — graceful error fallback

Observability:
- Intent classification logged at INFO with result
- LLM failures logged at WARNING with fallback trigger
- Sub-agent errors logged at ERROR
- PII redaction: only user_id is logged, never email or name
"""

import os
import logging
import json
from datetime import datetime
from typing import Literal, Optional, Dict, Any

from src.chat_agent.state import ChatAgentState
from src.chat_agent.smartapply_client import SmartApplyClient

logger = logging.getLogger(__name__)

# ── Intent classification constants ──────────────────────────────────────────

# Keyword-based fallback: specific immigration terms to avoid collision
# with the services intent.
_RCIC_KEYWORDS = ["visa", "immigration", "rcic", "permit", "citizenship", "pr"]
_SMART_APPLY_KEYWORDS = ["school", "apply", "program", "university", "college"]
_SERVICES_KEYWORDS = ["service", "services"]

# LLM-based classification system prompt
_INTENT_CLASSIFICATION_PROMPT = """\
You are an intent classifier for a Canadian education and immigration assistant.
Classify the user's message into exactly ONE of these intents:

- smart_apply: The user wants to find schools, apply to programs, get school
  recommendations, or anything related to finding and applying to educational
  institutions.
- rcic: The user wants help with immigration matters — visas, permits, PR
  (permanent residency), citizenship, or needs advice from a Regulated Canadian
  Immigration Consultant.
- services: The user is asking about what services are available, general
  information about the platform, pricing, or features.
- unclear: The message is a greeting, off-topic, or too vague to classify.

Respond with ONLY the intent name — nothing else. Examples:
  "I want to find schools in Canada" → smart_apply
  "help me with my study permit" → rcic
  "what do you offer?" → services
  "hello" → unclear
"""


def classify_intent(state: ChatAgentState) -> dict:
    """
    Classify user intent from the last message using LLM with keyword fallback.

    Strategy:
    1. Try LLM-based classification (Google Gemini if available)
    2. If LLM fails (no API key, timeout, error), fall back to keyword heuristic

    Returns:
        State update with intent and current_step set.
    """
    messages = state.get("messages", [])
    last_message = _extract_last_user_message(messages)
    message_lower = last_message.lower()

    # Try LLM classification first
    intent = _classify_with_llm(message_lower)

    # Fall back to keyword heuristic if LLM didn't return a valid intent
    if intent not in ("smart_apply", "rcic", "services", "unclear"):
        intent = _classify_with_keywords(message_lower)
        logger.warning(
            "classify_intent: LLM classification failed, "
            "falling back to keyword heuristic"
        )

    logger.info(
        f"Intent classified: intent={intent}, "
        f"message_preview={last_message[:80]!r}"
    )

    return {
        "intent": intent,
        "current_step": "intent_classified",
    }


def _classify_with_llm(message: str) -> str:
    """
    Classify intent using Google Gemini LLM.

    Returns one of: smart_apply, rcic, services, unclear
    Returns "unknown" if the LLM call fails (triggers keyword fallback).
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.debug("classify_intent: no GOOGLE_API_KEY, skipping LLM")
        return "unknown"

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = (
            _INTENT_CLASSIFICATION_PROMPT
            + f"\n\nUser message: {message}\nIntent:"
        )

        response = model.generate_content(prompt)
        result = response.text.strip().lower()

        # Extract the intent name from the response
        for valid in ("smart_apply", "rcic", "services", "unclear"):
            if valid in result:
                return valid

        logger.warning(
            f"LLM returned unexpected intent value: {result!r}"
        )
        return "unknown"

    except Exception as exc:
        logger.warning(
            f"LLM classification failed: {exc} — will use keyword fallback"
        )
        return "unknown"


def _classify_with_keywords(message: str) -> str:
    """
    Keyword-based intent classification fallback.

    Order matters: more specific checks first to avoid collisions.
    Case-insensitive matching.
    """
    message = message.lower()
    if any(kw in message for kw in _SMART_APPLY_KEYWORDS):
        return "smart_apply"
    elif any(kw in message for kw in _RCIC_KEYWORDS):
        return "rcic"
    elif any(kw in message for kw in _SERVICES_KEYWORDS):
        return "services"
    else:
        return "unclear"


# ── Routing ──────────────────────────────────────────────────────────────────

def route_intent(
    state: ChatAgentState,
) -> Literal[
    "call_smart_apply", "call_services_stub", "call_rcic_stub", "ask_clarification"
]:
    """
    Conditional edge function: route based on classified intent.

    Returns:
        Next node name based on state["intent"].
    """
    intent = state.get("intent", "unclear")

    routing_map = {
        "smart_apply": "call_smart_apply",
        "services": "call_services_stub",
        "rcic": "call_rcic_stub",
        "unclear": "ask_clarification",
    }

    target = routing_map.get(intent, "ask_clarification")
    logger.info(f"Routing intent={intent} → node={target}")
    return target


def route_after_smart_apply(
    state: ChatAgentState,
) -> Literal["relay_question", "handle_sub_agent_error", "__end__"]:
    """
    Conditional edge function: route after call_smart_apply completes.

    Routing logic:
    - If Smart Apply returned requires_user_input=True → route to relay_question
    - If error_message is present → route to handle_sub_agent_error
    - Otherwise → route to END

    Returns:
        Next node name based on sub_agent_response and error state.
    """
    sub_agent_response = state.get("sub_agent_response") or {}
    error_message = state.get("error_message")

    if sub_agent_response.get("requires_user_input"):
        reason = sub_agent_response.get("interrupt_reason", "unknown")
        logger.info(
            f"route_after_smart_apply: requires_user_input=True, "
            f"routing to relay_question (reason={reason!r})"
        )
        return "relay_question"

    if error_message:
        logger.info(
            f"route_after_smart_apply: error_message present, "
            f"routing to handle_sub_agent_error"
        )
        return "handle_sub_agent_error"

    logger.info(f"route_after_smart_apply: routing to __end__")
    return "__end__"


# ── Multi-turn relay ────────────────────────────────────────────────────────

def relay_question(state: ChatAgentState) -> dict:
    """
    Relay Smart Apply's interrupt question to the user as an assistant message.

    When Smart Apply returns requires_user_input=True (e.g., a profile question
    or approval request), this node extracts the response text and formats it
    as an assistant message so the user sees the question in the chat.

    Returns:
        State update with messages containing the assistant question,
        and current_step set to "question_relayed".
    """
    sub_agent_response = state.get("sub_agent_response") or {}
    response_text = sub_agent_response.get("response", "")
    interrupt_reason = sub_agent_response.get("interrupt_reason", "unknown")

    assistant_msg = {
        "role": "assistant",
        "content": response_text,
        "timestamp": datetime.utcnow().isoformat(),
    }

    question_preview = response_text[:100]
    logger.info(
        f"relay_question: relaying Smart Apply question "
        f"(reason={interrupt_reason!r}, preview={question_preview!r})"
    )

    return {
        "messages": [assistant_msg],
        "needs_user_input": True,
        "current_step": "question_relayed",
    }


# ── Sub-agent calls ──────────────────────────────────────────────────────────

def call_smart_apply(state: ChatAgentState) -> dict:
    """
    Call the Smart Apply sub-agent via HTTP using SmartApplyClient.

    Multi-turn support:
    - Detects resume turns (needs_user_input=True) and forwards user_response
    - When Smart Apply returns requires_user_input=True, sets needs_user_input
      and skips assistant message formatting (relay_question node handles it)
    - When requires_user_input=False, formats the assistant message as before

    Handles:
    - Successful response → extracts and returns sub_agent_response
    - Structured 400 error → returns error_message in state
    - Timeout / 5xx / network failure → sets error_message for error handler

    Returns:
        State update with sub_agent_response, needs_user_input, or error_message.
    """
    user_message = _extract_last_user_message(state.get("messages", []))
    session_id = state.get("session_id", "default")
    user_context = state.get("user_context") or {}

    # Detect multi-turn resume: extract user response if Smart Apply paused
    user_response = _extract_user_response_for_resume(state)

    safe_user_id = str(user_context.get("user_id", "anonymous"))
    logger.info(
        f"call_smart_apply: invoking Smart Apply sub-agent, "
        f"user_id={safe_user_id}, session_id={session_id!r}, "
        f"resume={user_response is not None}"
    )

    import asyncio

    try:
        # Run the async HTTP client in the current event loop
        result = asyncio.get_event_loop().run_until_complete(
            _call_smart_apply_async(
                message=user_message,
                session_id=session_id,
                user_context=user_context,
                user_response=user_response,
            )
        )
    except RuntimeError:
        # No running event loop — create a new one
        result = asyncio.run(
            _call_smart_apply_async(
                message=user_message,
                session_id=session_id,
                user_context=user_context,
                user_response=user_response,
            )
        )

    if result is None:
        # All retries exhausted or unexpected failure (should not happen now
        # since SmartApplyClient always returns a dict, but keep as fallback)
        error_msg = (
            f"Smart Apply sub-agent call failed after all retries "
            f"(session_id={session_id!r})"
        )
        logger.error(f"call_smart_apply: {error_msg}")
        return {
            "error_message": error_msg,
            "error_type": "unknown",
            "current_step": "smart_apply_error",
        }

    # Check if the result contains an error_message (structured error or 400)
    if result.get("error_message"):
        error_type = result.get("error_type", "unknown")
        logger.error(
            f"call_smart_apply: structured error from Smart Apply: "
            f"error_type={error_type} message={result['error_message']}"
        )
        return {
            "sub_agent_response": result,
            "error_message": result["error_message"],
            "error_type": error_type,
            "current_step": "smart_apply_error",
        }

    # ── Interrupt detection: Smart Apply needs user input ──
    if result.get("requires_user_input"):
        logger.info(
            f"call_smart_apply: Smart Apply requires user input, "
            f"reason={result.get('interrupt_reason')!r}, "
            f"current_step={result.get('current_step', 'unknown')}"
        )
        return {
            "sub_agent_response": result,
            "needs_user_input": True,
            "current_step": "smart_apply_waiting_for_user",
        }

    # Successful response — format as assistant message
    response_text = result.get("response", "Smart Apply processed your request.")
    assistant_msg = {
        "role": "assistant",
        "content": response_text,
        "timestamp": datetime.utcnow().isoformat(),
    }

    logger.info(
        f"call_smart_apply: success, current_step={result.get('current_step', 'unknown')}"
    )

    return {
        "messages": [assistant_msg],
        "sub_agent_response": result,
        "needs_user_input": False,
        "current_step": "smart_apply_called",
    }




def call_services_stub(state: ChatAgentState) -> dict:
    """
    Call the Services sub-agent.

    Stub: returns a helpful "coming soon" message explaining what's coming
    and suggesting alternative intents the user can try right now.
    """
    message = (
        "Our full services catalog — including pricing, platform features, "
        "and support options — is coming soon! "
        "In the meantime, I can help you find schools and programs, "
        "or assist with Canadian immigration questions."
    )
    logger.info("call_services_stub: Services sub-agent not yet implemented")
    return {
        "messages": [{
            "role": "assistant",
            "content": message,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "sub_agent_response": {
            "agent": "services",
            "message": message,
            "status": "stub",
            "available_alternatives": [
                {
                    "intent": "smart_apply",
                    "label": "Find schools and programs",
                    "example": "I want to find schools in Canada",
                },
                {
                    "intent": "rcic",
                    "label": "Get immigration help",
                    "example": "Help me with my study permit",
                },
            ],
        },
        "current_step": "services_called",
    }


def call_rcic_stub(state: ChatAgentState) -> dict:
    """
    Call the RCIC (immigration) sub-agent.

    Stub: returns a helpful "coming soon" message explaining what's coming
    and suggesting alternative intents the user can try right now.
    """
    message = (
        "Our regulated Canadian immigration consultant (RCIC) service is "
        "coming soon! You'll be able to get expert help with visas, permits, "
        "permanent residency, and citizenship applications. "
        "In the meantime, I can help you find schools or learn about "
        "our available services."
    )
    logger.info("call_rcic_stub: RCIC sub-agent stub invoked")
    return {
        "messages": [{
            "role": "assistant",
            "content": message,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "sub_agent_response": {
            "agent": "rcic",
            "message": message,
            "status": "stub",
            "available_alternatives": [
                {
                    "intent": "smart_apply",
                    "label": "Find schools and programs",
                    "example": "I want to find schools in Canada",
                },
                {
                    "intent": "services",
                    "label": "Explore available services",
                    "example": "What services do you offer?",
                },
            ],
        },
        "current_step": "rcic_called",
    }


# ── Clarification and error handling ─────────────────────────────────────────

def ask_clarification(state: ChatAgentState) -> dict:
    """
    Ask a clarifying question when intent is unclear.

    Provides helpful examples to guide the user toward a classifiable intent.
    """
    clarification = (
        "I'm not sure what you need help with. Could you clarify? "
        "For example: 'I want to find schools', 'help me with immigration', "
        "or 'what services do you offer?'"
    )
    logger.info("ask_clarification: intent unclear, asking clarifying question")
    return {
        "messages": [{
            "role": "assistant",
            "content": clarification,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "current_step": "clarification_asked",
    }


def handle_sub_agent_error(state: ChatAgentState) -> dict:
    """
    Graceful error handler for sub-agent failures.

    Dispatches based on error_type to produce type-specific user messages:
    - timeout: service was slow, suggest retry
    - connection: network issue, suggest checking connectivity
    - server_error: backend problem, suggest retry shortly
    - not_found: configuration issue, generic message
    - bad_request: user input issue, suggest checking input
    - unknown: fallback generic error message

    Logs the error_type at ERROR level for observability.
    """
    error_msg = state.get("error_message", "Unknown sub-agent error")
    error_type = state.get("error_type", "unknown")

    logger.error(
        f"handle_sub_agent_error: error_type={error_type} message={error_msg}"
    )

    # Type-specific user messages
    user_messages = {
        "timeout": (
            "The Smart Apply service took too long to respond. "
            "This can happen during high traffic. Please try again in a moment."
        ),
        "connection": (
            "Unable to connect to the Smart Apply service. "
            "Please check your network connection and try again."
        ),
        "server_error": (
            "The Smart Apply service encountered an internal error. "
            "Please try again shortly."
        ),
        "not_found": (
            "The Smart Apply service is currently unavailable. "
            "We're working on it — please try again later."
        ),
        "bad_request": (
            "Your request could not be processed. "
            "Please check your input and try again."
        ),
        "unknown": (
            f"Sorry, I encountered an error: {error_msg}. Please try again."
        ),
    }

    user_message = user_messages.get(error_type, user_messages["unknown"])

    return {
        "messages": [{
            "role": "assistant",
            "content": user_message,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "current_step": "error_handled",
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_last_user_message(messages: list) -> str:
    """Extract the last user message content from a messages list."""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _extract_user_response_for_resume(state: ChatAgentState) -> Optional[str]:
    """
    Extract the user's reply for a multi-turn Smart Apply resume.

    When needs_user_input is True (Smart Apply paused awaiting user input
    like a profile question or approval), this returns the last user
    message content from the conversation history.

    Returns:
        The user's reply text, or None if not in a resume context.
    """
    if not state.get("needs_user_input"):
        return None

    last_user_msg = _extract_last_user_message(state.get("messages", []))
    if last_user_msg:
        logger.info(
            f"_extract_user_response_for_resume: resuming with "
            f"user_response={last_user_msg[:80]!r}"
        )
        return last_user_msg

    return None


async def _call_smart_apply_async(
    message: str,
    session_id: str,
    user_context: Optional[Dict[str, Any]],
    user_response: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Async wrapper for the Smart Apply HTTP call.

    Args:
        message: The user's chat message text.
        session_id: Unique session identifier for conversation continuity.
        user_context: Optional context dict from Go middleware.
        user_response: User's reply to forward on resume turns (multi-turn).
    """
    # Forward user_response into context for the Smart Apply API
    if user_response is not None:
        if user_context is None:
            user_context = {}
        user_context = dict(user_context)  # shallow copy to avoid mutation
        user_context["user_response"] = user_response

    async with SmartApplyClient() as client:
        return await client.chat(
            message=message,
            session_id=session_id,
            user_context=user_context,
        )
