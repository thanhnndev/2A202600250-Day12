"""
LangGraph state graph wiring for Smart Apply agent.

Defines the complete workflow with human-in-the-loop interrupts:
Profile Collector → School Finder → Human Approval (interrupt) → Document Generator
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.graph.state import AgentState
from src.graph.nodes import (
    profile_collector,
    school_finder,
    human_approval,
    document_generator,
    route_human_approval,
    route_after_profile_collection
)
import logging

logger = logging.getLogger(__name__)


def create_agent_graph() -> StateGraph:
    """
    Create and compile the Smart Apply agent graph with human interrupts.
    
    Graph structure:
    ```
    [START] → profile_collector → school_finder → human_approval
                                                    ↓ interrupt()
                                            (user provides feedback)
                                                    ↓
                                            route_after_approval
                                            ↓ yes        ↓ no
                                    document_generator   school_finder
                                            ↓
                                          [END]
    ```
    """
    # Initialize graph with AgentState
    graph_builder = StateGraph(AgentState)
    
    # Add nodes
    graph_builder.add_node("profile_collector", profile_collector)
    graph_builder.add_node("school_finder", school_finder)
    graph_builder.add_node("human_approval", human_approval)
    graph_builder.add_node("document_generator", document_generator)
    
    # Set entry point
    graph_builder.set_entry_point("profile_collector")
    
    # Add conditional edge after profile_collector
    # Route based on whether profile is complete or needs more info
    graph_builder.add_conditional_edges(
        "profile_collector",
        route_after_profile_collection,
        {
            "continue": "school_finder",
            "ask_question": END  # End to wait for user input
        }
    )
    
    graph_builder.add_edge("school_finder", "human_approval")
    
    # Add conditional edge after human_approval
    # Route based on user's approval decision
    graph_builder.add_conditional_edges(
        "human_approval",
        route_human_approval,
        {
            "document_generator": "document_generator",
            "school_finder": "school_finder"
        }
    )
    
    graph_builder.add_edge("document_generator", END)
    
    # Add memory checkpoint for persistence across interrupts
    memory = MemorySaver()
    
    # Compile graph with interrupt configuration
    compiled_graph = graph_builder.compile(
        checkpointer=memory,
        interrupt_before=["human_approval"]  # Interrupt before human_approval node
    )
    
    return compiled_graph


# Global graph instance
agent_graph = create_agent_graph()


def run_agent(user_input: str, session_id: str = "default", thread_id: str = "default") -> dict:
    """
    Run the agent with user input and support for interrupts.
    
    Args:
        user_input: Initial user message or feedback
        session_id: Unique session identifier
        thread_id: Thread ID for conversation continuity (used with checkpointer)
    
    Returns:
        Current state with all messages and results
    """
    from datetime import datetime
    from src.graph.state import Message
    
    # Configuration for thread
    config = {"configurable": {"thread_id": thread_id}}
    
    # Get current state
    current_state = agent_graph.get_state(config)
    
    if current_state.next:  # If we're resuming from an interrupt
        logger.info(f"Resuming from interrupt at node: {current_state.next}")
        
        # Add user feedback to state
        updated_values = {
            "messages": [
                Message(
                    role="user",
                    content=user_input,
                    timestamp=datetime.utcnow().isoformat()
                )
            ],
            "user_feedback": user_input,
            "needs_user_input": False,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Update state with user feedback
        agent_graph.update_state(config, updated_values)
        
        # Continue execution from where it left off
        final_state = agent_graph.invoke(None, config)
    else:
        # Initialize new state
        initial_state: AgentState = {
            "messages": [
                Message(
                    role="user",
                    content=user_input,
                    timestamp=datetime.utcnow().isoformat()
                )
            ],
            "user_profile": {},
            "schools": [],
            "selected_schools": [],
            "pdf_path": None,
            "pdf_generated": False,
            "current_step": "collecting_profile",
            "needs_user_input": False,
            "user_feedback": None,
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        
        # Run graph
        final_state = agent_graph.invoke(initial_state, config)
    
    return final_state
