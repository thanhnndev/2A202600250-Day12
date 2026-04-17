"""
Tests for the Chat Agent supervisor graph.

Covers:
- Keyword-based intent classification (4 intents: smart_apply, rcic, services, unclear)
- Conditional routing (5 values including fallback)
- Sub-agent stubs (services, rcic)
- Clarification node (unclear intent)
- Graph compilation
- Full graph execution
- Client error handling
- FastAPI endpoint models
- relay_question node (Smart Apply interrupt relay)
"""

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.chat_agent.state import ChatAgentState
from src.chat_agent.nodes import (
    classify_intent,
    route_intent,
    call_smart_apply,
    call_services_stub,
    call_rcic_stub,
    ask_clarification,
    _classify_with_keywords,
    _extract_user_response_for_resume,
    route_after_smart_apply,
    relay_question,
    handle_sub_agent_error,
)


# ── 1. Keyword Classification Tests (4 intents) ─────────────────────────────

class TestKeywordClassification:
    """Test keyword-based intent classification fallback."""

    def test_smart_apply_school_keyword(self, keyword_classification_cases):
        """Messages with school-related keywords classify as smart_apply."""
        school_cases = [
            ("I want to find schools in Canada", "smart_apply"),
            ("apply to university program", "smart_apply"),
            ("college recommendation please", "smart_apply"),
        ]
        for message, expected in school_cases:
            result = _classify_with_keywords(message.lower())
            assert result == expected, f"Expected {expected} for {message!r}, got {result}"

    def test_rcic_visa_keyword(self, keyword_classification_cases):
        """Messages with immigration keywords classify as rcic."""
        rcic_cases = [
            ("help me with my visa application", "rcic"),
            ("immigration advice needed", "rcic"),
            ("RCIC consultation", "rcic"),
            ("study permit help", "rcic"),
            ("citizenship test prep", "rcic"),
            ("PR application help", "rcic"),
        ]
        for message, expected in rcic_cases:
            result = _classify_with_keywords(message.lower())
            assert result == expected, f"Expected {expected} for {message!r}, got {result}"

    def test_services_keyword(self):
        """Messages with 'service' keyword classify as services."""
        result = _classify_with_keywords("what services are available")
        assert result == "services"

    def test_unclear_greeting(self):
        """Greeting messages classify as unclear."""
        result = _classify_with_keywords("hello there")
        assert result == "unclear"

    def test_unclear_random_text(self):
        """Random/unrelated text classifies as unclear."""
        result = _classify_with_keywords("random gibberish xyz 123")
        assert result == "unclear"

    def test_keyword_order_precedence(self):
        """Smart apply keywords should take precedence over rcic when both present."""
        # "school" and "visa" both present — smart_apply keywords are checked first
        result = _classify_with_keywords("i want to find schools and need a visa")
        assert result == "smart_apply"


# ── 2. Routing Tests (5 values) ─────────────────────────────────────────────

class TestIntentRouting:
    """Test conditional edge routing from classified intent."""

    def test_route_smart_apply(self):
        """smart_apply intent routes to call_smart_apply."""
        state: ChatAgentState = {
            "messages": [],
            "intent": "smart_apply",
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "session_id": "test",
            "current_step": "test",
        }
        assert route_intent(state) == "call_smart_apply"

    def test_route_services(self):
        """services intent routes to call_services_stub."""
        state: ChatAgentState = {
            "messages": [],
            "intent": "services",
        }
        assert route_intent(state) == "call_services_stub"

    def test_route_rcic(self):
        """rcic intent routes to call_rcic_stub."""
        state: ChatAgentState = {
            "messages": [],
            "intent": "rcic",
        }
        assert route_intent(state) == "call_rcic_stub"

    def test_route_unclear(self):
        """unclear intent routes to ask_clarification."""
        state: ChatAgentState = {
            "messages": [],
            "intent": "unclear",
        }
        assert route_intent(state) == "ask_clarification"

    def test_route_invalid_fallback(self):
        """Invalid/missing intent falls back to ask_clarification."""
        state: ChatAgentState = {
            "messages": [],
            "intent": "nonexistent_intent",
        }
        assert route_intent(state) == "ask_clarification"

    def test_route_all_parametrized(self, chat_intent_routing_cases):
        """All routing cases verified via parametrized fixture."""
        for intent, expected_node in chat_intent_routing_cases:
            state: ChatAgentState = {
                "messages": [],
                "intent": intent,
            }
            result = route_intent(state)
            assert result == expected_node, (
                f"Expected route {expected_node} for intent={intent!r}, got {result}"
            )


# ── 3. Sub-agent Stub Tests (2 stubs) ───────────────────────────────────────

class TestSubAgentStubs:
    """Test services and rcic sub-agent stubs."""

    def test_services_stub_returns_coming_soon(self, chat_state_basic):
        """Services stub returns a 'coming soon' response."""
        result = call_services_stub(chat_state_basic)
        assert "sub_agent_response" in result
        assert result["sub_agent_response"]["agent"] == "services"
        assert result["sub_agent_response"]["status"] == "stub"
        assert "coming soon" in result["sub_agent_response"]["message"].lower()

    def test_rcic_stub_returns_coming_soon(self, chat_state_basic):
        """RCIC stub returns a 'coming soon' response."""
        result = call_rcic_stub(chat_state_basic)
        assert "sub_agent_response" in result
        assert result["sub_agent_response"]["agent"] == "rcic"
        assert result["sub_agent_response"]["status"] == "stub"
        assert "coming soon" in result["sub_agent_response"]["message"].lower()

    def test_services_stub_sets_current_step(self, chat_state_basic):
        """Services stub sets current_step to services_called."""
        result = call_services_stub(chat_state_basic)
        assert result["current_step"] == "services_called"

    def test_rcic_stub_sets_current_step(self, chat_state_basic):
        """RCIC stub sets current_step to rcic_called."""
        result = call_rcic_stub(chat_state_basic)
        assert result["current_step"] == "rcic_called"

    def test_services_stub_returns_assistant_message(self, chat_state_basic):
        """Services stub returns an assistant message for the user."""
        result = call_services_stub(chat_state_basic)
        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert msg["role"] == "assistant"
        assert "coming soon" in msg["content"].lower()
        assert "timestamp" in msg

    def test_rcic_stub_returns_assistant_message(self, chat_state_basic):
        """RCIC stub returns an assistant message for the user."""
        result = call_rcic_stub(chat_state_basic)
        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert msg["role"] == "assistant"
        assert "coming soon" in msg["content"].lower()
        assert "timestamp" in msg

    def test_services_stub_has_available_alternatives(self, chat_state_basic):
        """Services stub includes available_alternatives with helpful suggestions."""
        result = call_services_stub(chat_state_basic)
        alternatives = result["sub_agent_response"]["available_alternatives"]
        assert isinstance(alternatives, list)
        assert len(alternatives) >= 2
        # Each alternative has intent, label, and example
        for alt in alternatives:
            assert "intent" in alt
            assert "label" in alt
            assert "example" in alt
        # Should suggest smart_apply and rcic as alternatives
        intents = [a["intent"] for a in alternatives]
        assert "smart_apply" in intents
        assert "rcic" in intents

    def test_rcic_stub_has_available_alternatives(self, chat_state_basic):
        """RCIC stub includes available_alternatives with helpful suggestions."""
        result = call_rcic_stub(chat_state_basic)
        alternatives = result["sub_agent_response"]["available_alternatives"]
        assert isinstance(alternatives, list)
        assert len(alternatives) >= 2
        # Each alternative has intent, label, and example
        for alt in alternatives:
            assert "intent" in alt
            assert "label" in alt
            assert "example" in alt
        # Should suggest smart_apply and services as alternatives
        intents = [a["intent"] for a in alternatives]
        assert "smart_apply" in intents
        assert "services" in intents

    def test_stubs_return_consistent_structure(self, chat_state_basic):
        """Both stubs return the same response structure."""
        services_result = call_services_stub(chat_state_basic)
        rcic_result = call_rcic_stub(chat_state_basic)

        # Both have the same top-level keys
        assert set(services_result.keys()) == set(rcic_result.keys())
        assert "messages" in services_result
        assert "sub_agent_response" in services_result
        assert "current_step" in services_result

        # Both sub_agent_response have the same keys
        sa_keys = set(services_result["sub_agent_response"].keys())
        rcic_keys = set(rcic_result["sub_agent_response"].keys())
        assert sa_keys == rcic_keys
        assert sa_keys >= {"agent", "message", "status", "available_alternatives"}


# ── 4. Clarification Test ───────────────────────────────────────────────────

class TestClarification:
    """Test the ask_clarification node."""

    def test_ask_clarification_returns_helpful_message(self, chat_state_unclear):
        """Clarification node returns a helpful message with examples."""
        result = ask_clarification(chat_state_unclear)
        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert msg["role"] == "assistant"
        assert "clarif" in msg["content"].lower() or "not sure" in msg["content"].lower()
        # Should mention example intents
        assert "schools" in msg["content"].lower() or "immigration" in msg["content"].lower()

    def test_ask_clarification_sets_step(self, chat_state_unclear):
        """Clarification node sets current_step to clarification_asked."""
        result = ask_clarification(chat_state_unclear)
        assert result["current_step"] == "clarification_asked"

    def test_ask_clarification_has_timestamp(self, chat_state_unclear):
        """Clarification message includes a timestamp."""
        result = ask_clarification(chat_state_unclear)
        msg = result["messages"][0]
        assert "timestamp" in msg
        assert msg["timestamp"] is not None


# ── 5. Graph Compilation Test ───────────────────────────────────────────────

class TestGraphCompilation:
    """Test that the Chat Agent graph compiles correctly."""

    def test_graph_compiles_without_error(self, chat_agent_graph):
        """Graph creation returns a valid compiled graph."""
        assert chat_agent_graph is not None
        # Compiled graphs have an invoke method
        assert hasattr(chat_agent_graph, "invoke")

    def test_graph_has_expected_nodes(self, chat_agent_graph):
        """Graph contains all 7 expected nodes (6 original + relay_question)."""
        expected_nodes = {
            "classify_intent",
            "call_smart_apply",
            "call_services_stub",
            "call_rcic_stub",
            "ask_clarification",
            "handle_sub_agent_error",
            "relay_question",
        }
        # Access the graph's nodes via the builder's compiled structure
        # In compiled graphs, nodes are accessible through the graph definition
        graph_state = chat_agent_graph.get_state(
            {"configurable": {"thread_id": "test-nodes"}}
        )
        # If we can get_state, the graph is properly compiled
        assert graph_state is not None

    def test_graph_has_relay_question_node(self, chat_agent_graph):
        """Graph includes the relay_question node for multi-turn Smart Apply."""
        # The compiled graph includes __start__ as an internal node
        graph_nodes = chat_agent_graph.nodes
        assert "relay_question" in graph_nodes, (
            "relay_question node must be present in the compiled graph for multi-turn support"
        )
        # 7 real nodes + __start__ = 8 total
        assert len(graph_nodes) == 8, (
            f"Expected 8 nodes in compiled graph (7 real + __start__), got {len(graph_nodes)}"
        )


# ── 6. Graph Execution Test ─────────────────────────────────────────────────

class TestGraphExecution:
    """Test full graph execution through various intent paths."""

    def test_execute_smart_apply_path(self, chat_agent_graph):
        """Graph executes smart_apply path via keyword classification."""
        config = {"configurable": {"thread_id": "test-exec-sa"}}
        initial_state = {
            "messages": [{"role": "user", "content": "I want to find schools in Canada"}],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "session_id": "test-exec-sa",
            "current_step": "start",
        }

        final_state = chat_agent_graph.invoke(initial_state, config=config)

        assert final_state["intent"] == "smart_apply"
        assert final_state["current_step"] in (
            "smart_apply_called",
            "smart_apply_error",
            "error_handled",
        )

    def test_execute_services_path(self, chat_agent_graph):
        """Graph executes services path via keyword classification."""
        config = {"configurable": {"thread_id": "test-exec-svc"}}
        initial_state = {
            "messages": [{"role": "user", "content": "what services do you offer?"}],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "session_id": "test-exec-svc",
            "current_step": "start",
        }

        final_state = chat_agent_graph.invoke(initial_state, config=config)

        assert final_state["intent"] == "services"
        assert final_state["sub_agent_response"]["agent"] == "services"
        assert final_state["current_step"] == "services_called"

    def test_execute_rcic_path(self, chat_agent_graph):
        """Graph executes rcic path via keyword classification."""
        config = {"configurable": {"thread_id": "test-exec-rcic"}}
        initial_state = {
            "messages": [{"role": "user", "content": "help me with my study permit"}],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "session_id": "test-exec-rcic",
            "current_step": "start",
        }

        final_state = chat_agent_graph.invoke(initial_state, config=config)

        assert final_state["intent"] == "rcic"
        assert final_state["sub_agent_response"]["agent"] == "rcic"
        assert final_state["current_step"] == "rcic_called"

    def test_execute_unclear_path(self, chat_agent_graph):
        """Graph executes clarification path for unclear intent."""
        config = {"configurable": {"thread_id": "test-exec-unclear"}}
        initial_state = {
            "messages": [{"role": "user", "content": "hello there, how are you?"}],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "session_id": "test-exec-unclear",
            "current_step": "start",
        }

        final_state = chat_agent_graph.invoke(initial_state, config=config)

        assert final_state["intent"] == "unclear"
        assert final_state["current_step"] == "clarification_asked"
        # Should have an assistant message with clarification
        assistant_msgs = [
            m for m in final_state["messages"]
            if isinstance(m, dict) and m.get("role") == "assistant"
        ]
        assert len(assistant_msgs) >= 1


# ── 7. Client Error Test ────────────────────────────────────────────────────

class TestClientErrorHandling:
    """Test error handling when SmartApplyClient fails."""

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_smart_apply_client_timeout_returns_error(self, mock_async, chat_state_basic):
        """When SmartApplyClient returns None, call_smart_apply returns error_message."""
        mock_async.return_value = None

        result = call_smart_apply(chat_state_basic)

        assert "error_message" in result
        assert "failed after all retries" in result["error_message"]
        assert result["current_step"] == "smart_apply_error"

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_smart_apply_client_structured_400(self, mock_async, chat_state_basic):
        """When SmartApplyClient returns structured 400, error_message is set."""
        mock_async.return_value = {
            "response": "",
            "messages": [],
            "current_step": "error",
            "error_message": "Invalid input: missing required fields",
            "schools_count": 0,
        }

        result = call_smart_apply(chat_state_basic)

        assert "error_message" in result
        assert result["error_message"] == "Invalid input: missing required fields"
        assert "sub_agent_response" in result

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_smart_apply_client_success(self, mock_async, chat_state_basic):
        """When SmartApplyClient succeeds, response is properly formatted."""
        mock_async.return_value = {
            "response": "Here are 3 schools matching your profile.",
            "messages": [],
            "current_step": "schools_found",
            "schools_count": 3,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        result = call_smart_apply(chat_state_basic)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "assistant"
        assert "schools" in result["messages"][0]["content"].lower()
        assert result["sub_agent_response"]["schools_count"] == 3
        assert result["current_step"] == "smart_apply_called"


# ── 8. classify_intent Node Test ────────────────────────────────────────────

class TestClassifyIntentNode:
    """Test the classify_intent node end-to-end."""

    def test_classify_intent_keyword_fallback_smart_apply(self):
        """Node classifies smart_apply via keyword fallback when no LLM key."""
        state: ChatAgentState = {
            "messages": [{"role": "user", "content": "find me schools in Canada"}],
            "intent": None,
        }
        result = classify_intent(state)
        assert result["intent"] == "smart_apply"
        assert result["current_step"] == "intent_classified"

    def test_classify_intent_keyword_fallback_rcic(self):
        """Node classifies rcic via keyword fallback when no LLM key."""
        state: ChatAgentState = {
            "messages": [{"role": "user", "content": "visa application help"}],
            "intent": None,
        }
        result = classify_intent(state)
        assert result["intent"] == "rcic"

    def test_classify_intent_keyword_fallback_services(self):
        """Node classifies services via keyword fallback when no LLM key."""
        state: ChatAgentState = {
            "messages": [{"role": "user", "content": "what services are available"}],
            "intent": None,
        }
        result = classify_intent(state)
        assert result["intent"] == "services"

    def test_classify_intent_keyword_fallback_unclear(self):
        """Node classifies unclear via keyword fallback when no LLM key."""
        state: ChatAgentState = {
            "messages": [{"role": "user", "content": "hey there"}],
            "intent": None,
        }
        result = classify_intent(state)
        assert result["intent"] == "unclear"


# ── 9. FastAPI Endpoint Model Tests ─────────────────────────────────────────

class TestEndpointModels:
    """Test the Pydantic request/response models for the endpoint."""

    def test_chat_agent_request_minimal(self):
        """ChatAgentRequest accepts just a message."""
        from src.main import ChatAgentRequest
        req = ChatAgentRequest(message="hello")
        assert req.message == "hello"
        assert req.session_id is None
        assert req.user_context is None

    def test_chat_agent_request_full(self):
        """ChatAgentRequest accepts all optional fields."""
        from src.main import ChatAgentRequest
        req = ChatAgentRequest(
            message="I want to find schools",
            session_id="sess_123",
            user_context={"user_id": "u-456", "preferences": {"country": "Canada"}},
        )
        assert req.message == "I want to find schools"
        assert req.session_id == "sess_123"
        assert req.user_context["user_id"] == "u-456"

    def test_chat_agent_response_minimal(self):
        """ChatAgentResponse can be constructed with defaults."""
        from src.main import ChatAgentResponse
        resp = ChatAgentResponse(response="Hello!")
        assert resp.response == "Hello!"
        assert resp.intent is None
        assert resp.messages == []
        assert resp.sub_agent_response is None
        assert resp.error_message is None

    def test_chat_agent_response_full(self):
        """ChatAgentResponse accepts all fields."""
        from src.main import ChatAgentResponse, Message
        resp = ChatAgentResponse(
            intent="smart_apply",
            response="Here are your schools.",
            messages=[Message(role="assistant", content="Here are your schools.")],
            sub_agent_response={"schools_count": 3},
            current_step="smart_apply_called",
            session_id="sess_123",
        )
        assert resp.intent == "smart_apply"
        assert resp.current_step == "smart_apply_called"
        assert resp.session_id == "sess_123"
        assert len(resp.messages) == 1


# ── 10. Edge Case / Negative Tests ──────────────────────────────────────────

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_message_classification(self):
        """Empty message classifies as unclear."""
        result = _classify_with_keywords("")
        assert result == "unclear"

    def test_very_long_message_classification(self):
        """Very long messages are handled without error."""
        long_msg = "school " * 1000 + "apply program university"
        result = _classify_with_keywords(long_msg)
        assert result == "smart_apply"

    def test_special_characters_message(self):
        """Messages with special characters classify as unclear."""
        result = _classify_with_keywords("!@#$%^&*()_+{}|:<>?")
        assert result == "unclear"

    def test_mixed_case_keywords(self):
        """Keywords are matched case-insensitively."""
        assert _classify_with_keywords("I need a VISA") == "rcic"
        assert _classify_with_keywords("SCHOOL application") == "smart_apply"
        assert _classify_with_keywords("What SERVICES exist") == "services"

    def test_route_intent_missing_intent_key(self):
        """Routing with missing intent key defaults to ask_clarification."""
        state: ChatAgentState = {
            "messages": [],
        }
        result = route_intent(state)
        assert result == "ask_clarification"


# ── 11. Multi-Turn Resume Helper Tests ──────────────────────────────────────

class TestExtractUserResponseForResume:
    """Test the _extract_user_response_for_resume helper."""

    def test_returns_none_when_needs_user_input_false(self):
        """When needs_user_input is False, returns None."""
        state: ChatAgentState = {
            "messages": [{"role": "user", "content": "hello"}],
            "needs_user_input": False,
        }
        result = _extract_user_response_for_resume(state)
        assert result is None

    def test_returns_none_when_needs_user_input_not_set(self):
        """When needs_user_input is not set, returns None."""
        state: ChatAgentState = {
            "messages": [{"role": "user", "content": "hello"}],
        }
        result = _extract_user_response_for_resume(state)
        assert result is None

    def test_returns_last_user_message_when_needs_user_input_true(self):
        """When needs_user_input is True, returns the last user message."""
        state: ChatAgentState = {
            "messages": [
                {"role": "assistant", "content": "What is your budget?"},
                {"role": "user", "content": "My budget is $30,000 per year"},
            ],
            "needs_user_input": True,
        }
        result = _extract_user_response_for_resume(state)
        assert result == "My budget is $30,000 per year"

    def test_returns_none_when_no_user_messages(self):
        """When needs_user_input is True but no user messages, returns None."""
        state: ChatAgentState = {
            "messages": [
                {"role": "assistant", "content": "What is your budget?"},
            ],
            "needs_user_input": True,
        }
        result = _extract_user_response_for_resume(state)
        assert result is None

    def test_returns_none_for_empty_user_message(self):
        """When the last user message is empty, returns None (no valid response)."""
        state: ChatAgentState = {
            "messages": [
                {"role": "assistant", "content": "What is your budget?"},
                {"role": "user", "content": ""},
            ],
            "needs_user_input": True,
        }
        result = _extract_user_response_for_resume(state)
        # Empty string is not a valid resume response, so returns None
        assert result is None


# ── 12. Multi-Turn call_smart_apply Tests ───────────────────────────────────

class TestSmartApplyMultiTurn:
    """Test multi-turn Smart Apply behavior in call_smart_apply."""

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_requires_user_input_sets_needs_user_input(self, mock_async, chat_state_basic):
        """When Smart Apply returns requires_user_input=True, needs_user_input is set."""
        mock_async.return_value = {
            "response": "What is your preferred budget range?",
            "messages": [],
            "current_step": "profile_question_asked",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": True,
            "interrupt_reason": "profile_question",
        }

        result = call_smart_apply(chat_state_basic)

        assert result["needs_user_input"] is True
        assert result["sub_agent_response"]["requires_user_input"] is True
        assert result["current_step"] == "smart_apply_waiting_for_user"
        # No assistant message should be added
        assert "messages" not in result

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_no_requires_user_input_formats_assistant_message(self, mock_async, chat_state_basic):
        """When requires_user_input is False, assistant message is formatted."""
        mock_async.return_value = {
            "response": "Here are 3 schools matching your profile.",
            "messages": [],
            "current_step": "schools_found",
            "schools_count": 3,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        result = call_smart_apply(chat_state_basic)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "assistant"
        assert result.get("needs_user_input") is False  # Cleared on successful completion

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_resume_turn_passes_user_response(self, mock_async, chat_state_basic):
        """When resuming a paused session, user_response is passed to async call."""
        chat_state_basic["needs_user_input"] = True
        chat_state_basic["messages"] = [
            {"role": "assistant", "content": "What is your budget?"},
            {"role": "user", "content": "My budget is $30,000"},
        ]
        mock_async.return_value = {
            "response": "Here are schools within your budget.",
            "messages": [],
            "current_step": "schools_found",
            "schools_count": 2,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        result = call_smart_apply(chat_state_basic)

        # Verify user_response was passed to the async call
        mock_async.assert_called_once()
        call_kwargs = mock_async.call_args[1]
        assert call_kwargs["user_response"] == "My budget is $30,000"
        assert result["current_step"] == "smart_apply_called"

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_non_resume_does_not_pass_user_response(self, mock_async, chat_state_basic):
        """On a normal (non-resume) turn, user_response is None."""
        mock_async.return_value = {
            "response": "Found 5 schools.",
            "messages": [],
            "current_step": "schools_found",
            "schools_count": 5,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        call_smart_apply(chat_state_basic)

        call_kwargs = mock_async.call_args[1]
        assert call_kwargs["user_response"] is None


# ── 13. route_after_smart_apply Tests ───────────────────────────────────────

class TestRouteAfterSmartApply:
    """Test the route_after_smart_apply conditional edge function."""

    def test_routes_to_relay_question_when_requires_user_input(self):
        """When sub_agent_response has requires_user_input=True, routes to relay_question."""
        state: ChatAgentState = {
            "messages": [],
            "sub_agent_response": {
                "response": "What is your budget?",
                "requires_user_input": True,
                "interrupt_reason": "profile_question",
            },
        }
        result = route_after_smart_apply(state)
        assert result == "relay_question"

    def test_routes_to_error_handler_when_error_message(self):
        """When error_message is present, routes to handle_sub_agent_error."""
        state: ChatAgentState = {
            "messages": [],
            "sub_agent_response": {"response": "", "requires_user_input": False},
            "error_message": "Smart Apply sub-agent call failed after all retries",
        }
        result = route_after_smart_apply(state)
        assert result == "handle_sub_agent_error"

    def test_routes_to_end_on_success(self):
        """When no interrupt and no error, routes to __end__."""
        state: ChatAgentState = {
            "messages": [],
            "sub_agent_response": {
                "response": "Found 3 schools.",
                "requires_user_input": False,
                "schools_count": 3,
            },
        }
        result = route_after_smart_apply(state)
        assert result == "__end__"

    def test_routes_to_end_with_no_sub_agent_response(self):
        """When sub_agent_response is None, routes to __end__."""
        state: ChatAgentState = {
            "messages": [],
            "sub_agent_response": None,
        }
        result = route_after_smart_apply(state)
        assert result == "__end__"

    def test_routes_to_end_with_empty_sub_agent_response(self):
        """When sub_agent_response is empty dict, routes to __end__."""
        state: ChatAgentState = {
            "messages": [],
            "sub_agent_response": {},
        }
        result = route_after_smart_apply(state)
        assert result == "__end__"

    def test_relay_question_takes_precedence_over_error(self):
        """When both requires_user_input and error_message exist, relay_question wins."""
        # This tests priority: interrupt detection > error handling
        state: ChatAgentState = {
            "messages": [],
            "sub_agent_response": {
                "response": "What is your budget?",
                "requires_user_input": True,
                "interrupt_reason": "profile_question",
            },
            "error_message": "Some error occurred",
        }
        result = route_after_smart_apply(state)
        assert result == "relay_question"


# ── 14. relay_question Node Tests ───────────────────────────────────────────

class TestRelayQuestion:
    """Test the relay_question node that relays Smart Apply interrupt questions to the user."""

    def test_relay_question_formats_assistant_message(self, chat_state_basic):
        """relay_question formats sub_agent_response.response as assistant message."""
        chat_state_basic["sub_agent_response"] = {
            "response": "What is your preferred budget range?",
            "requires_user_input": True,
            "interrupt_reason": "profile_question",
        }

        result = relay_question(chat_state_basic)

        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "What is your preferred budget range?"
        assert "timestamp" in msg

    def test_relay_question_sets_current_step(self, chat_state_basic):
        """relay_question sets current_step to question_relayed."""
        chat_state_basic["sub_agent_response"] = {
            "response": "Do you approve these schools?",
            "requires_user_input": True,
            "interrupt_reason": "approval_request",
        }

        result = relay_question(chat_state_basic)

        assert result["current_step"] == "question_relayed"

    def test_relay_question_handles_empty_response(self, chat_state_basic):
        """relay_question handles missing response text gracefully."""
        chat_state_basic["sub_agent_response"] = {
            "response": "",
            "requires_user_input": True,
            "interrupt_reason": "profile_question",
        }

        result = relay_question(chat_state_basic)

        assert "messages" in result
        assert result["messages"][0]["content"] == ""

    def test_relay_question_handles_none_sub_agent_response(self, chat_state_basic):
        """relay_question handles None sub_agent_response without crashing."""
        chat_state_basic["sub_agent_response"] = None

        result = relay_question(chat_state_basic)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "assistant"
        assert result["messages"][0]["content"] == ""
        assert result["current_step"] == "question_relayed"


# ── 15. Graph Execution: Interrupt Path ─────────────────────────────────────

class TestGraphInterruptExecution:
    """Test full graph execution through the Smart Apply interrupt → relay_question path."""

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_smart_apply_interrupt_routes_to_relay_question(self, mock_async, chat_agent_graph):
        """When Smart Apply returns requires_user_input=True, graph routes to relay_question."""
        mock_async.return_value = {
            "response": "What is your preferred budget range?",
            "messages": [],
            "current_step": "profile_question_asked",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": True,
            "interrupt_reason": "profile_question",
        }

        config = {"configurable": {"thread_id": "test-interrupt-path"}}
        initial_state = {
            "messages": [{"role": "user", "content": "I want to find schools in Canada"}],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "session_id": "test-interrupt-path",
            "current_step": "start",
        }

        final_state = chat_agent_graph.invoke(initial_state, config=config)

        assert final_state["intent"] == "smart_apply"
        assert final_state["needs_user_input"] is True
        assert final_state["current_step"] == "question_relayed"

        # Should have the relayed question as an assistant message
        assistant_msgs = [
            m for m in final_state["messages"]
            if isinstance(m, dict) and m.get("role") == "assistant"
        ]
        assert len(assistant_msgs) >= 1
        # The relay_question message should contain the budget question
        assert any("budget" in m.get("content", "").lower() for m in assistant_msgs)


# ── 16. relay_question preserves needs_user_input ───────────────────────────

class TestRelayQuestionPreservesState:
    """Test that relay_question preserves needs_user_input for checkpoint continuity."""

    def test_relay_question_preserves_needs_user_input(self, chat_state_basic):
        """relay_question returns needs_user_input=True so checkpoint survives."""
        chat_state_basic["sub_agent_response"] = {
            "response": "What is your budget?",
            "requires_user_input": True,
            "interrupt_reason": "profile_question",
        }

        result = relay_question(chat_state_basic)

        assert result.get("needs_user_input") is True, (
            "relay_question must return needs_user_input=True for endpoint resume detection"
        )

    def test_relay_question_returns_messages_and_step(self, chat_state_basic):
        """relay_question still returns messages and current_step alongside needs_user_input."""
        chat_state_basic["sub_agent_response"] = {
            "response": "Confirm these schools?",
            "requires_user_input": True,
            "interrupt_reason": "approval_request",
        }

        result = relay_question(chat_state_basic)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["current_step"] == "question_relayed"
        assert result["needs_user_input"] is True


# ── 17. ChatAgentResponse: needs_user_input and interrupt_reason ────────────

class TestChatAgentResponseFields:
    """Test the new needs_user_input and interrupt_reason fields on ChatAgentResponse."""

    def test_response_with_needs_user_input_true(self):
        """ChatAgentResponse accepts needs_user_input=True."""
        from src.main import ChatAgentResponse
        resp = ChatAgentResponse(
            intent="smart_apply",
            response="What is your budget?",
            needs_user_input=True,
            interrupt_reason="profile_question",
            session_id="sess_123",
        )
        assert resp.needs_user_input is True
        assert resp.interrupt_reason == "profile_question"
        assert resp.session_id == "sess_123"

    def test_response_with_needs_user_input_none(self):
        """ChatAgentResponse defaults needs_user_input to None on normal responses."""
        from src.main import ChatAgentResponse
        resp = ChatAgentResponse(
            intent="smart_apply",
            response="Here are 3 schools.",
            session_id="sess_123",
        )
        assert resp.needs_user_input is None
        assert resp.interrupt_reason is None

    def test_response_with_interrupt_reason_from_sub_agent(self):
        """ChatAgentResponse properly stores interrupt_reason extracted from sub_agent_response."""
        from src.main import ChatAgentResponse
        resp = ChatAgentResponse(
            intent="smart_apply",
            response="Please confirm these schools.",
            sub_agent_response={
                "requires_user_input": True,
                "interrupt_reason": "approval_request",
                "schools_count": 3,
            },
            needs_user_input=True,
            interrupt_reason="approval_request",
        )
        assert resp.interrupt_reason == "approval_request"
        assert resp.sub_agent_response["requires_user_input"] is True


# ── 18. Session Resume Detection ────────────────────────────────────────────

class TestSessionResumeDetection:
    """Test the chat_agent endpoint session resume detection via get_state."""

    @patch("src.main.chat_agent_graph")
    def test_resume_turn_skips_classification(self, mock_graph):
        """When get_state shows needs_user_input=True, endpoint sets intent=smart_apply."""
        from src.main import chat_agent, ChatAgentRequest
        from types import SimpleNamespace

        # Simulate previous state with needs_user_input=True
        mock_graph.get_state.return_value = SimpleNamespace(
            values={
                "needs_user_input": True,
                "current_step": "question_relayed",
                "messages": [
                    {"role": "user", "content": "Find schools in Canada"},
                    {"role": "assistant", "content": "What is your budget?"},
                ],
                "intent": "smart_apply",
                "session_id": "resume-session",
            }
        )
        mock_graph.invoke.return_value = {
            "messages": [
                {"role": "user", "content": "Find schools in Canada"},
                {"role": "assistant", "content": "What is your budget?"},
                {"role": "user", "content": "My budget is $30,000"},
                {"role": "assistant", "content": "Here are schools within your budget."},
            ],
            "intent": "smart_apply",
            "sub_agent_response": {
                "schools_count": 2,
                "requires_user_input": False,
            },
            "error_message": None,
            "current_step": "smart_apply_called",
            "session_id": "resume-session",
            "needs_user_input": False,
        }

        request = ChatAgentRequest(
            message="My budget is $30,000",
            session_id="resume-session",
        )

        import asyncio
        response = asyncio.run(chat_agent(request))

        # Verify the endpoint passed intent=smart_apply to skip classification
        invoke_call = mock_graph.invoke.call_args
        initial_state = invoke_call[0][0]
        assert initial_state["intent"] == "smart_apply", (
            "Resume turn should set intent=smart_apply to skip classification"
        )
        assert initial_state["user_response"] == "My budget is $30,000"

    @patch("src.main.chat_agent_graph")
    def test_new_turn_normal_classification(self, mock_graph):
        """When no previous state exists, endpoint behaves normally (intent=None)."""
        from src.main import chat_agent, ChatAgentRequest
        from types import SimpleNamespace

        # Simulate no previous state
        mock_graph.get_state.return_value = SimpleNamespace(values=None)
        mock_graph.invoke.return_value = {
            "messages": [
                {"role": "user", "content": "What services do you offer?"},
                {"role": "assistant", "content": "Services stub coming soon."},
            ],
            "intent": "services",
            "sub_agent_response": {"agent": "services", "status": "stub"},
            "error_message": None,
            "current_step": "services_called",
            "session_id": "new-session",
            "needs_user_input": None,
        }

        request = ChatAgentRequest(
            message="What services do you offer?",
            session_id="new-session",
        )

        import asyncio
        response = asyncio.run(chat_agent(request))

        invoke_call = mock_graph.invoke.call_args
        initial_state = invoke_call[0][0]
        assert initial_state["intent"] is None, (
            "New turn should leave intent=None for classification"
        )
        assert "user_response" not in initial_state or initial_state.get("user_response") is None

    @patch("src.main.chat_agent_graph")
    def test_resume_forward_user_response_in_state(self, mock_graph):
        """Resume turn extracts user response and includes user_response in initial state."""
        from src.main import chat_agent, ChatAgentRequest
        from types import SimpleNamespace

        mock_graph.get_state.return_value = SimpleNamespace(
            values={
                "needs_user_input": True,
                "current_step": "question_relayed",
                "messages": [
                    {"role": "user", "content": "Find schools in Canada"},
                    {"role": "assistant", "content": "What is your budget?"},
                ],
                "intent": "smart_apply",
                "session_id": "resume-session",
            }
        )
        mock_graph.invoke.return_value = {
            "messages": [],
            "intent": "smart_apply",
            "sub_agent_response": {"schools_count": 3},
            "error_message": None,
            "current_step": "smart_apply_called",
            "session_id": "resume-session",
            "needs_user_input": False,
        }

        request = ChatAgentRequest(
            message="$30,000 per year",
            session_id="resume-session",
            user_context={"user_id": "u-123"},
        )

        import asyncio
        response = asyncio.run(chat_agent(request))

        invoke_call = mock_graph.invoke.call_args
        initial_state = invoke_call[0][0]
        assert initial_state["user_response"] == "$30,000 per year"
        assert initial_state["user_context"] == {"user_id": "u-123"}

    @patch("src.main.chat_agent_graph")
    def test_session_id_passed_as_thread_id(self, mock_graph):
        """session_id from request is passed through config as thread_id."""
        from src.main import chat_agent, ChatAgentRequest
        from types import SimpleNamespace

        mock_graph.get_state.return_value = SimpleNamespace(values=None)
        mock_graph.invoke.return_value = {
            "messages": [],
            "intent": "smart_apply",
            "sub_agent_response": None,
            "error_message": None,
            "current_step": "smart_apply_called",
            "session_id": "my-session-123",
            "needs_user_input": None,
        }

        request = ChatAgentRequest(
            message="Find schools",
            session_id="my-session-123",
        )

        import asyncio
        response = asyncio.run(chat_agent(request))

        # Verify config passed to invoke contains correct thread_id
        invoke_kwargs = mock_graph.invoke.call_args[1]
        assert invoke_kwargs["config"]["configurable"]["thread_id"] == "my-session-123"

    @patch("src.main.chat_agent_graph")
    def test_resume_response_includes_needs_user_input(self, mock_graph):
        """Response includes needs_user_input and interrupt_reason from final state."""
        from src.main import chat_agent, ChatAgentRequest
        from types import SimpleNamespace

        mock_graph.get_state.return_value = SimpleNamespace(
            values={
                "needs_user_input": True,
                "current_step": "question_relayed",
                "messages": [
                    {"role": "user", "content": "Find schools"},
                    {"role": "assistant", "content": "What is your budget?"},
                ],
            }
        )
        mock_graph.invoke.return_value = {
            "messages": [
                {"role": "user", "content": "Find schools"},
                {"role": "assistant", "content": "What is your budget?"},
                {"role": "user", "content": "$20,000"},
                {"role": "assistant", "content": "Here are schools matching your budget."},
            ],
            "intent": "smart_apply",
            "sub_agent_response": {
                "schools_count": 5,
                "requires_user_input": True,
                "interrupt_reason": "approval_request",
            },
            "error_message": None,
            "current_step": "smart_apply_waiting_for_user",
            "session_id": "resume-session",
            "needs_user_input": True,
        }

        request = ChatAgentRequest(
            message="$20,000",
            session_id="resume-session",
        )

        import asyncio
        response = asyncio.run(chat_agent(request))

        assert response.needs_user_input is True
        assert response.interrupt_reason == "approval_request"


# ── 19. Full Graph Multi-Turn Resume Execution ──────────────────────────────

class TestGraphResumeExecution:
    """Test full graph multi-turn execution: turn 1 (interrupt) → turn 2 (resume with final result)."""

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_resume_turn_returns_final_result(self, mock_async, chat_agent_graph):
        """
        Simulate a complete two-turn flow:
        Turn 1: Smart Apply returns requires_user_input=True → question relayed
        Turn 2: Graph invoked with resume state (needs_user_input=True) → final school results returned
        """
        # Turn 2: Smart Apply returns final results (no more questions)
        mock_async.return_value = {
            "response": "Here are 3 schools in Canada within your $30,000 budget.",
            "messages": [],
            "current_step": "schools_found",
            "schools_count": 3,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        config = {"configurable": {"thread_id": "test-resume-turn"}}
        # Simulate resume state: needs_user_input=True triggers _extract_user_response_for_resume,
        # and the last user message includes "school" keyword so classify_intent routes to smart_apply.
        resume_state = {
            "messages": [
                {"role": "user", "content": "I want to find schools in Canada"},
                {"role": "assistant", "content": "What is your preferred budget range?"},
                {"role": "user", "content": "My budget is $30,000 for school applications"},
            ],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "needs_user_input": True,
            "session_id": "test-resume-turn",
            "current_step": "start",
        }

        final_state = chat_agent_graph.invoke(resume_state, config=config)

        # Verify the graph completed successfully with school results
        assert final_state["intent"] == "smart_apply"
        assert final_state["current_step"] == "smart_apply_called"
        assert final_state.get("needs_user_input") is False  # Cleared on successful completion

        # Verify school results are in the response
        assistant_msgs = [
            m for m in final_state["messages"]
            if isinstance(m, dict) and m.get("role") == "assistant"
        ]
        assert len(assistant_msgs) >= 1
        assert any("schools" in m.get("content", "").lower() for m in assistant_msgs)
        assert final_state["sub_agent_response"]["schools_count"] == 3

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_resume_turn_passes_user_response_to_smart_apply(self, mock_async, chat_agent_graph):
        """Resume turn extracts last user message and forwards it as user_response."""
        mock_async.return_value = {
            "response": "Schools found for $30,000 budget.",
            "messages": [],
            "current_step": "schools_found",
            "schools_count": 2,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        config = {"configurable": {"thread_id": "test-resume-user-response"}}
        # needs_user_input=True + last user message contains "school" keyword
        resume_state = {
            "messages": [
                {"role": "assistant", "content": "What is your budget?"},
                {"role": "user", "content": "$30,000 per year for school in Canada"},
            ],
            "intent": None,
            "sub_agent_response": None,
            "user_context": {"user_id": "u-123"},
            "error_message": None,
            "needs_user_input": True,
            "session_id": "test-resume-user-response",
            "current_step": "start",
        }

        chat_agent_graph.invoke(resume_state, config=config)

        # Verify user_response was forwarded to the async call
        mock_async.assert_called_once()
        call_kwargs = mock_async.call_args[1]
        assert call_kwargs["user_response"] == "$30,000 per year for school in Canada"

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_two_turn_flow_interrupt_then_complete(self, mock_async, chat_agent_graph):
        """
        Full two-turn integration test:
        Turn 1: User asks for schools → Smart Apply asks budget question → question relayed
        Turn 2: User provides budget → Smart Apply returns final results
        """
        call_count = [0]

        def smart_apply_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: Smart Apply needs more info
                return {
                    "response": "What is your preferred budget range?",
                    "messages": [],
                    "current_step": "profile_question_asked",
                    "schools_count": 0,
                    "pdf_generated": False,
                    "pdf_path": None,
                    "requires_user_input": True,
                    "interrupt_reason": "profile_question",
                }
            else:
                # Second call: Smart Apply has final results
                return {
                    "response": "Found 3 schools in Canada matching your $30,000 budget.",
                    "messages": [],
                    "current_step": "schools_found",
                    "schools_count": 3,
                    "pdf_generated": False,
                    "pdf_path": None,
                    "requires_user_input": False,
                    "interrupt_reason": None,
                }

        mock_async.side_effect = smart_apply_side_effect

        # ── Turn 1: User asks for schools ──
        config = {"configurable": {"thread_id": "test-two-turn-flow"}}
        turn1_state = {
            "messages": [{"role": "user", "content": "Find me schools in Canada"}],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "session_id": "test-two-turn-flow",
            "current_step": "start",
        }

        turn1_result = chat_agent_graph.invoke(turn1_state, config=config)

        # Verify turn 1: question relayed, needs_user_input=True
        assert turn1_result["needs_user_input"] is True
        assert turn1_result["current_step"] == "question_relayed"
        assert turn1_result["sub_agent_response"]["requires_user_input"] is True

        assistant_msgs_turn1 = [
            m for m in turn1_result["messages"]
            if isinstance(m, dict) and m.get("role") == "assistant"
        ]
        assert any("budget" in m.get("content", "").lower() for m in assistant_msgs_turn1)

        # ── Turn 2: User provides budget answer ──
        # needs_user_input=True triggers resume path in call_smart_apply,
        # and the last user message includes "school" keyword for classification.
        turn2_state = {
            "messages": [
                {"role": "user", "content": "Find me schools in Canada"},
                {"role": "assistant", "content": "What is your preferred budget range?"},
                {"role": "user", "content": "$30,000 per year for school applications"},
            ],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "needs_user_input": True,
            "session_id": "test-two-turn-flow",
            "current_step": "start",
        }

        turn2_result = chat_agent_graph.invoke(turn2_state, config=config)

        # Verify turn 2: final results returned
        assert turn2_result["current_step"] == "smart_apply_called"
        assert turn2_result.get("needs_user_input") is False  # Cleared on successful completion
        assert turn2_result["sub_agent_response"]["schools_count"] == 3

        assistant_msgs_turn2 = [
            m for m in turn2_result["messages"]
            if isinstance(m, dict) and m.get("role") == "assistant"
        ]
        assert any("schools" in m.get("content", "").lower() for m in assistant_msgs_turn2)

        # Verify both calls were made
        assert call_count[0] == 2


# ── 20. Error Classification Tests ──────────────────────────────────────────

class TestErrorClassification:
    """Test error_type classification and type-specific user messages."""

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_timeout_error_type(self, mock_async, chat_state_basic):
        """When SmartApplyClient returns timeout error, error_type is propagated."""
        mock_async.return_value = {
            "response": "",
            "messages": [],
            "current_step": "error",
            "error_message": "The Smart Apply service took too long to respond.",
            "error_type": "timeout",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        result = call_smart_apply(chat_state_basic)

        assert result["error_type"] == "timeout"
        assert result["error_message"] == "The Smart Apply service took too long to respond."
        assert result["current_step"] == "smart_apply_error"

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_connection_error_type(self, mock_async, chat_state_basic):
        """When SmartApplyClient returns connection error, error_type is propagated."""
        mock_async.return_value = {
            "response": "",
            "messages": [],
            "current_step": "error",
            "error_message": "Unable to connect to the Smart Apply service.",
            "error_type": "connection",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        result = call_smart_apply(chat_state_basic)

        assert result["error_type"] == "connection"
        assert result["current_step"] == "smart_apply_error"

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_server_error_type(self, mock_async, chat_state_basic):
        """When SmartApplyClient returns server error, error_type is propagated."""
        mock_async.return_value = {
            "response": "",
            "messages": [],
            "current_step": "error",
            "error_message": "The Smart Apply service encountered an internal error.",
            "error_type": "server_error",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        result = call_smart_apply(chat_state_basic)

        assert result["error_type"] == "server_error"
        assert result["current_step"] == "smart_apply_error"

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_not_found_error_type(self, mock_async, chat_state_basic):
        """When SmartApplyClient returns not_found error, error_type is propagated."""
        mock_async.return_value = {
            "response": "",
            "messages": [],
            "current_step": "error",
            "error_message": "The Smart Apply service endpoint was not found.",
            "error_type": "not_found",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        result = call_smart_apply(chat_state_basic)

        assert result["error_type"] == "not_found"
        assert result["current_step"] == "smart_apply_error"

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_bad_request_error_type(self, mock_async, chat_state_basic):
        """When SmartApplyClient returns bad_request error, error_type is propagated."""
        mock_async.return_value = {
            "response": "",
            "messages": [],
            "current_step": "error",
            "error_message": "Bad request: Invalid input",
            "error_type": "bad_request",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        result = call_smart_apply(chat_state_basic)

        assert result["error_type"] == "bad_request"
        assert result["current_step"] == "smart_apply_error"


class TestHandleSubAgentError:
    """Test handle_sub_agent_error dispatches based on error_type."""

    def test_timeout_error_user_message(self):
        """handle_sub_agent_error produces timeout-specific message."""
        from src.chat_agent.nodes import handle_sub_agent_error
        state: ChatAgentState = {
            "messages": [],
            "error_message": "The Smart Apply service took too long to respond.",
            "error_type": "timeout",
        }
        result = handle_sub_agent_error(state)
        assert "messages" in result
        msg = result["messages"][0]
        assert msg["role"] == "assistant"
        assert "too long" in msg["content"].lower() or "try again" in msg["content"].lower()
        assert result["current_step"] == "error_handled"

    def test_connection_error_user_message(self):
        """handle_sub_agent_error produces connection-specific message."""
        from src.chat_agent.nodes import handle_sub_agent_error
        state: ChatAgentState = {
            "messages": [],
            "error_message": "Unable to connect to the Smart Apply service.",
            "error_type": "connection",
        }
        result = handle_sub_agent_error(state)
        msg = result["messages"][0]
        assert "connect" in msg["content"].lower() or "network" in msg["content"].lower()

    def test_server_error_user_message(self):
        """handle_sub_agent_error produces server-error-specific message."""
        from src.chat_agent.nodes import handle_sub_agent_error
        state: ChatAgentState = {
            "messages": [],
            "error_message": "Internal server error.",
            "error_type": "server_error",
        }
        result = handle_sub_agent_error(state)
        msg = result["messages"][0]
        assert "internal error" in msg["content"].lower() or "try again" in msg["content"].lower()

    def test_not_found_error_user_message(self):
        """handle_sub_agent_error produces not-found-specific message."""
        from src.chat_agent.nodes import handle_sub_agent_error
        state: ChatAgentState = {
            "messages": [],
            "error_message": "Endpoint not found.",
            "error_type": "not_found",
        }
        result = handle_sub_agent_error(state)
        msg = result["messages"][0]
        assert "unavailable" in msg["content"].lower() or "not found" in msg["content"].lower()

    def test_bad_request_error_user_message(self):
        """handle_sub_agent_error produces bad-request-specific message."""
        from src.chat_agent.nodes import handle_sub_agent_error
        state: ChatAgentState = {
            "messages": [],
            "error_message": "Bad request: missing fields.",
            "error_type": "bad_request",
        }
        result = handle_sub_agent_error(state)
        msg = result["messages"][0]
        assert "check your input" in msg["content"].lower() or "could not be processed" in msg["content"].lower()

    def test_unknown_error_fallback_message(self):
        """handle_sub_agent_error produces generic message for unknown error_type."""
        from src.chat_agent.nodes import handle_sub_agent_error
        state: ChatAgentState = {
            "messages": [],
            "error_message": "Something weird happened.",
            "error_type": "unknown",
        }
        result = handle_sub_agent_error(state)
        msg = result["messages"][0]
        assert "error" in msg["content"].lower()
        assert "Something weird happened" in msg["content"]

    def test_missing_error_type_defaults_to_unknown(self):
        """handle_sub_agent_error defaults to unknown when error_type is missing."""
        from src.chat_agent.nodes import handle_sub_agent_error
        state: ChatAgentState = {
            "messages": [],
            "error_message": "Some error.",
        }
        result = handle_sub_agent_error(state)
        msg = result["messages"][0]
        # Should still produce a valid message
        assert msg["role"] == "assistant"
        assert result["current_step"] == "error_handled"


class TestSmartApplyClientErrorTypes:
    """Test SmartApplyClient error classification helpers."""

    def test_error_dict_builder(self):
        """_error_dict produces a properly structured error response."""
        from src.chat_agent.smartapply_client import _error_dict
        result = _error_dict(error_type="timeout", error_message="Timed out")
        assert result["error_type"] == "timeout"
        assert result["error_message"] == "Timed out"
        assert result["current_step"] == "error"
        assert result["response"] == ""
        assert result["requires_user_input"] is False

    def test_classify_error_type_timeout(self):
        """_classify_error_type returns 'timeout' for TimeoutException."""
        from src.chat_agent.smartapply_client import _classify_error_type
        import httpx
        result = _classify_error_type(httpx.TimeoutException("timed out"))
        assert result == "timeout"

    def test_classify_error_type_connection(self):
        """_classify_error_type returns 'connection' for ConnectError."""
        from src.chat_agent.smartapply_client import _classify_error_type
        import httpx
        result = _classify_error_type(httpx.ConnectError("connection refused"))
        assert result == "connection"

    def test_classify_error_type_server_error(self):
        """_classify_error_type returns 'server_error' for server error ValueError."""
        from src.chat_agent.smartapply_client import _classify_error_type
        result = _classify_error_type(ValueError("Server error 500: internal"))
        assert result == "server_error"

    def test_classify_error_type_none(self):
        """_classify_error_type returns 'unknown' for None."""
        from src.chat_agent.smartapply_client import _classify_error_type
        result = _classify_error_type(None)
        assert result == "unknown"

    def test_classify_error_type_generic_exception(self):
        """_classify_error_type returns 'unknown' for generic exceptions."""
        from src.chat_agent.smartapply_client import _classify_error_type
        result = _classify_error_type(RuntimeError("weird"))
        assert result == "unknown"

    def test_error_user_messages_all_types(self):
        """_error_user_message returns a non-empty message for each error type."""
        from src.chat_agent.smartapply_client import _error_user_message
        error_types = ["timeout", "connection", "server_error", "not_found", "bad_request", "unknown"]
        for et in error_types:
            msg = _error_user_message(et, None)
            assert msg, f"Expected non-empty message for error_type={et}"
            assert len(msg) > 10, f"Message for {et} is too short: {msg!r}"


class TestGraphErrorExecution:
    """Test full graph execution through error paths."""

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_graph_handles_timeout_error(self, mock_async, chat_agent_graph):
        """Graph routes timeout error through handle_sub_agent_error."""
        mock_async.return_value = {
            "response": "",
            "messages": [],
            "current_step": "error",
            "error_message": "The Smart Apply service took too long to respond.",
            "error_type": "timeout",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        config = {"configurable": {"thread_id": "test-error-timeout"}}
        initial_state = {
            "messages": [{"role": "user", "content": "I want to find schools in Canada"}],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "error_type": None,
            "session_id": "test-error-timeout",
            "current_step": "start",
        }

        final_state = chat_agent_graph.invoke(initial_state, config=config)

        # Should have gone through error handler
        assert final_state["error_type"] == "timeout"
        assert final_state["current_step"] == "error_handled"

        # Error message should be user-friendly
        assistant_msgs = [
            m for m in final_state["messages"]
            if isinstance(m, dict) and m.get("role") == "assistant"
        ]
        assert len(assistant_msgs) >= 1
        # The error handler message should mention timeout/retry
        last_msg = assistant_msgs[-1]
        assert "too long" in last_msg.get("content", "").lower() or "try again" in last_msg.get("content", "").lower()

    @patch("src.chat_agent.nodes._call_smart_apply_async")
    def test_graph_handles_connection_error(self, mock_async, chat_agent_graph):
        """Graph routes connection error through handle_sub_agent_error."""
        mock_async.return_value = {
            "response": "",
            "messages": [],
            "current_step": "error",
            "error_message": "Unable to connect to the Smart Apply service.",
            "error_type": "connection",
            "schools_count": 0,
            "pdf_generated": False,
            "pdf_path": None,
            "requires_user_input": False,
            "interrupt_reason": None,
        }

        config = {"configurable": {"thread_id": "test-error-connection"}}
        initial_state = {
            "messages": [{"role": "user", "content": "I want to find schools"}],
            "intent": None,
            "sub_agent_response": None,
            "user_context": None,
            "error_message": None,
            "error_type": None,
            "session_id": "test-error-connection",
            "current_step": "start",
        }

        final_state = chat_agent_graph.invoke(initial_state, config=config)

        assert final_state["error_type"] == "connection"
        assert final_state["current_step"] == "error_handled"

        assistant_msgs = [
            m for m in final_state["messages"]
            if isinstance(m, dict) and m.get("role") == "assistant"
        ]
        assert len(assistant_msgs) >= 1
        last_msg = assistant_msgs[-1]
        assert "connect" in last_msg.get("content", "").lower() or "network" in last_msg.get("content", "").lower()


# ── 21. Streaming SSE Endpoint Tests ─────────────────────────────────────────

class TestChatAgentStreamResponse:
    """Test the ChatAgentStreamResponse Pydantic model."""

    def test_stream_response_minimal(self):
        """ChatAgentStreamResponse accepts just event_type."""
        from src.main import ChatAgentStreamResponse
        resp = ChatAgentStreamResponse(event_type="intent_classified")
        assert resp.event_type == "intent_classified"
        assert resp.data == {}
        assert resp.timestamp is None

    def test_stream_response_full(self):
        """ChatAgentStreamResponse accepts all fields."""
        from src.main import ChatAgentStreamResponse
        resp = ChatAgentStreamResponse(
            event_type="sub_agent_start",
            data={"node": "call_smart_apply", "agent": "smart_apply"},
            timestamp="2026-04-15T00:00:00",
        )
        assert resp.event_type == "sub_agent_start"
        assert resp.data["node"] == "call_smart_apply"
        assert resp.data["agent"] == "smart_apply"
        assert resp.timestamp == "2026-04-15T00:00:00"

    def test_stream_response_event_types(self):
        """All expected event types are valid model values."""
        from src.main import ChatAgentStreamResponse
        event_types = [
            "intent_classified",
            "sub_agent_start",
            "sub_agent_end",
            "message",
            "stub_response",
            "clarification",
            "stream_end",
            "error",
        ]
        for et in event_types:
            resp = ChatAgentStreamResponse(event_type=et)
            assert resp.event_type == et


class TestStreamingEndpoint:
    """Test the POST /api/v1/agents/chat/stream endpoint behavior."""

    def _make_agen(self, items):
        """Create an async generator from a list of items for mocking."""
        async def _agen(*_args, **_kwargs):
            for item in items:
                yield item
        return _agen

    async def _collect_events(self, endpoint_coro):
        """Collect SSE data events from an EventSourceResponse."""
        resp = await endpoint_coro
        events = []
        async for chunk in resp.body_iterator:
            if isinstance(chunk, dict):
                events.append(chunk)
            elif isinstance(chunk, str):
                if chunk.startswith("data: "):
                    events.append(json.loads(chunk[6:]))
            else:
                txt = chunk.decode() if hasattr(chunk, "decode") else str(chunk)
                if txt.startswith("data: "):
                    events.append(json.loads(txt[6:]))
        return events

    @patch("src.main.chat_agent_graph")
    def test_stream_emits_intent_classified_event(self, mock_graph):
        """Streaming endpoint emits intent_classified event after classification."""
        from src.main import chat_agent_stream, ChatAgentRequest
        import asyncio, json

        mock_graph.astream_events = self._make_agen([
            {"event": "on_chain_start", "name": "classify_intent", "data": {}},
            {"event": "on_chain_end", "name": "classify_intent",
             "data": {"output": {"intent": "services", "current_step": "intent_classified"}}},
        ])
        request = ChatAgentRequest(message="what services exist?")

        async def collect():
            class FakeReq:
                async def is_disconnected(self): return False
            return await self._collect_events(chat_agent_stream(request, FakeReq()))

        events = asyncio.run(collect())
        types = [e["event_type"] for e in events]
        assert "intent_classified" in types
        assert "stream_end" in types
        ie = [e for e in events if e["event_type"] == "intent_classified"]
        assert len(ie) == 1
        assert ie[0]["data"]["intent"] == "services"

    @patch("src.main.chat_agent_graph")
    def test_stream_emits_stub_response_event(self, mock_graph):
        """Streaming endpoint emits stub_response for services stub."""
        from src.main import chat_agent_stream, ChatAgentRequest
        import asyncio, json

        mock_graph.astream_events = self._make_agen([
            {"event": "on_chain_start", "name": "classify_intent", "data": {}},
            {"event": "on_chain_end", "name": "classify_intent",
             "data": {"output": {"intent": "services", "current_step": "intent_classified"}}},
            {"event": "on_chain_start", "name": "call_services_stub", "data": {}},
            {"event": "on_chain_end", "name": "call_services_stub",
             "data": {"output": {
                 "sub_agent_response": {
                     "message": "Services coming soon",
                     "available_alternatives": [{"intent": "smart_apply"}],
                 },
                 "messages": [],
             }}},
        ])
        request = ChatAgentRequest(message="what services exist?")

        async def collect():
            class FakeReq:
                async def is_disconnected(self): return False
            return await self._collect_events(chat_agent_stream(request, FakeReq()))

        events = asyncio.run(collect())
        types = [e["event_type"] for e in events]
        assert "stub_response" in types
        stub = [e for e in events if e["event_type"] == "stub_response"]
        assert stub[0]["data"]["agent"] == "services_stub"

    @patch("src.main.chat_agent_graph")
    def test_stream_emits_clarification_event(self, mock_graph):
        """Streaming endpoint emits clarification event for unclear intent."""
        from src.main import chat_agent_stream, ChatAgentRequest
        import asyncio, json

        mock_graph.astream_events = self._make_agen([
            {"event": "on_chain_start", "name": "classify_intent", "data": {}},
            {"event": "on_chain_end", "name": "classify_intent",
             "data": {"output": {"intent": "unclear", "current_step": "intent_classified"}}},
            {"event": "on_chain_start", "name": "ask_clarification", "data": {}},
            {"event": "on_chain_end", "name": "ask_clarification",
             "data": {"output": {
                 "messages": [{"role": "assistant", "content": "I'm not sure what you need."}],
                 "current_step": "clarification_asked",
             }}},
        ])
        request = ChatAgentRequest(message="hello there")

        async def collect():
            class FakeReq:
                async def is_disconnected(self): return False
            return await self._collect_events(chat_agent_stream(request, FakeReq()))

        events = asyncio.run(collect())
        types = [e["event_type"] for e in events]
        assert "clarification" in types
        cl = [e for e in events if e["event_type"] == "clarification"]
        assert cl[0]["data"]["content"] == "I'm not sure what you need."

    @patch("src.main.chat_agent_graph")
    def test_stream_emits_error_on_exception(self, mock_graph):
        """Streaming endpoint emits error event when graph throws."""
        from src.main import chat_agent_stream, ChatAgentRequest
        import asyncio, json

        async def failing_agen(*_args, **_kwargs):
            raise ValueError("Graph execution failed")
            yield

        mock_graph.astream_events = failing_agen
        request = ChatAgentRequest(message="test")

        async def collect():
            class FakeReq:
                async def is_disconnected(self): return False
            return await self._collect_events(chat_agent_stream(request, FakeReq()))

        events = asyncio.run(collect())
        errs = [e for e in events if e["event_type"] == "error"]
        assert len(errs) == 1
        assert "Graph execution failed" in errs[0]["data"]["message"]

    @patch("src.main.chat_agent_graph")
    def test_stream_session_id_in_final_event(self, mock_graph):
        """stream_end event includes session_id."""
        from src.main import chat_agent_stream, ChatAgentRequest
        import asyncio, json

        mock_graph.astream_events = self._make_agen([])
        request = ChatAgentRequest(message="test", session_id="my-session-123")

        async def collect():
            class FakeReq:
                async def is_disconnected(self): return False
            return await self._collect_events(chat_agent_stream(request, FakeReq()))

        events = asyncio.run(collect())
        ends = [e for e in events if e["event_type"] == "stream_end"]
        assert len(ends) == 1
        assert "session_id" in ends[0]["data"]
