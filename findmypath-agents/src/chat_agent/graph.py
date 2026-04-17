"""
LangGraph supervisor graph for the Chat Agent.

Wires a 7-node graph that classifies user intent and routes to the correct
sub-agent (Smart Apply via HTTP, Services stub, RCIC stub).

Graph structure:
    [START] → classify_intent
                  ↓ conditional edge (route_intent)
         ┌────────┼────────┬────────────┐
         ↓        ↓        ↓            ↓
    call_smart_apply  call_services  call_rcic_stub
         ↓ conditional     ↓            ↓
    (route_after_smart_apply)
         ↓
    ┌────┼────────────┐
    ↓    ↓            ↓
 relay_question  call_rcic_stub  ask_clarification
    ↓    ↓            ↓            ↓
    └────┼────────────┘            ↓
         ↓                         ↓
    handle_sub_agent_error         ↓
         ↓                         ↓
       [END] ←─────────────────────┘

Node implementations live in src/chat_agent/nodes.py.
"""

import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.chat_agent.state import ChatAgentState
from src.chat_agent.nodes import (
    classify_intent,
    route_intent,
    call_smart_apply,
    route_after_smart_apply,
    relay_question,
    call_services_stub,
    call_rcic_stub,
    ask_clarification,
    handle_sub_agent_error,
)

logger = logging.getLogger(__name__)


def create_chat_agent_graph() -> StateGraph:
    """
    Create and compile the Chat Agent supervisor graph.

    Graph structure:
        [START] → classify_intent → {route_intent conditional edge}
            → call_smart_apply → {route_after_smart_apply conditional edge}
                → relay_question → [END]
                → handle_sub_agent_error → [END]
                → [END] (direct success)
            → call_services_stub → [END]
            → call_rcic_stub → [END]
            → ask_clarification → [END]

    Uses MemorySaver for checkpoint persistence across turns.
    """
    graph_builder = StateGraph(ChatAgentState)

    # Register all 7 nodes (implemented in nodes.py)
    graph_builder.add_node("classify_intent", classify_intent)
    graph_builder.add_node("call_smart_apply", call_smart_apply)
    graph_builder.add_node("relay_question", relay_question)
    graph_builder.add_node("call_services_stub", call_services_stub)
    graph_builder.add_node("call_rcic_stub", call_rcic_stub)
    graph_builder.add_node("ask_clarification", ask_clarification)
    graph_builder.add_node("handle_sub_agent_error", handle_sub_agent_error)

    # Entry point
    graph_builder.set_entry_point("classify_intent")

    # Conditional routing after intent classification
    graph_builder.add_conditional_edges(
        "classify_intent",
        route_intent,
        {
            "call_smart_apply": "call_smart_apply",
            "call_services_stub": "call_services_stub",
            "call_rcic_stub": "call_rcic_stub",
            "ask_clarification": "ask_clarification",
        },
    )

    # Conditional routing after Smart Apply call
    # Routes to: relay_question (interrupt), handle_sub_agent_error (error), or END (success)
    graph_builder.add_conditional_edges(
        "call_smart_apply",
        route_after_smart_apply,
        {
            "relay_question": "relay_question",
            "handle_sub_agent_error": "handle_sub_agent_error",
            "__end__": END,
        },
    )

    # Stub nodes flow to END
    graph_builder.add_edge("call_services_stub", END)
    graph_builder.add_edge("call_rcic_stub", END)
    graph_builder.add_edge("ask_clarification", END)

    # Relay and error handlers flow to END
    graph_builder.add_edge("relay_question", END)
    graph_builder.add_edge("handle_sub_agent_error", END)

    # Memory checkpoint for conversation continuity
    memory = MemorySaver()

    # Compile the graph
    compiled_graph = graph_builder.compile(checkpointer=memory)

    logger.info("Chat agent graph compiled successfully")
    return compiled_graph
