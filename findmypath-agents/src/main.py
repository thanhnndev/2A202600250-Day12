"""
FastAPI service for Smart Apply LangGraph agents.

Endpoints:
- POST /api/v1/smartapply/agents/chat - Chat with Smart Apply agent
- POST /api/v1/smartapply/agents/chat/stream - Chat with streaming response (SSE)
- POST /api/v1/agents/chat - Chat with supervisor agent (intent classification + routing)
- GET /api/v1/smartapply/agents/pdf/:filename - Download generated PDF
- GET /health - Health check
- GET /docs - Swagger documentation
"""

import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field
import json
import logging

from dotenv import load_dotenv
load_dotenv()

from src.graph.graph import create_agent_graph, run_agent
from src.chat_agent.graph import create_chat_agent_graph

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Request/Response models
class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    user_response: Optional[str] = Field(None, description="User response for human-in-the-loop interactions")
    user_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Context from Go JWT middleware (user_id, email, name, timezone)"
    )


class Message(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    messages: list[Message] = []
    current_step: str
    schools_count: int = 0
    pdf_generated: bool = False
    pdf_path: Optional[str] = None
    requires_user_input: bool = False
    interrupt_reason: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


# ── Chat Agent (supervisor graph) request/response models ────────────────────

class ChatAgentRequest(BaseModel):
    """Request for the Chat Agent supervisor endpoint."""
    message: str = Field(..., description="User message to classify and route")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    user_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Context from Go JWT middleware (user_id, preferences, etc.)"
    )


class ChatAgentStreamResponse(BaseModel):
    """SSE event payload for the streaming chat agent endpoint."""
    event_type: str = Field(..., description="Type of streaming event")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event payload")
    timestamp: Optional[str] = Field(None, description="ISO-8601 timestamp")


class ChatAgentResponse(BaseModel):
    """Response from the Chat Agent supervisor endpoint."""
    intent: Optional[str] = Field(None, description="Classified intent")
    response: str = Field("", description="Assistant's reply text")
    messages: list[Message] = Field(default_factory=list, description="Conversation history")
    sub_agent_response: Optional[Dict[str, Any]] = Field(None, description="Raw sub-agent response")
    error_message: Optional[str] = Field(None, description="Error description if sub-agent failed")
    current_step: Optional[str] = Field(None, description="Current graph step")
    session_id: Optional[str] = Field(None, description="Session ID used for this request")
    needs_user_input: Optional[bool] = Field(None, description="True when Smart Apply paused awaiting user input")
    interrupt_reason: Optional[str] = Field(None, description="Reason for the Smart Apply interrupt (e.g., profile_question, approval_request)")


# Global graph instances
agent_graph = create_agent_graph()
chat_agent_graph = create_chat_agent_graph()


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("🚀 Smart Apply Agents service starting...")
    logger.info(f"   OpenAI Model: {os.getenv('OPENAI_MODEL', 'gpt-4-turbo-preview')}")
    logger.info(f"   Go Backend URL: {os.getenv('GO_BACKEND_URL', 'http://localhost:8080')}")
    yield
    # Shutdown
    logger.info("👋 Smart Apply Agents service shutting down...")


# Initialize FastAPI app
app = FastAPI(
    title="Smart Apply Agents API",
    description="LangGraph-powered school recommendation agent service",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_initial_state(request: ChatRequest, session_id: str) -> dict:
    """Build the initial agent state for a new conversation."""
    from src.graph.state import Message as StateMessage
    messages = [
        StateMessage(
            role="user",
            content=request.message,
            timestamp=datetime.utcnow().isoformat()
        )
    ]
    if request.user_response:
        messages.append(
            StateMessage(
                role="user",
                content=request.user_response,
                timestamp=datetime.utcnow().isoformat()
            )
        )
    return {
        "messages": messages,
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
        "updated_at": None,
        "interrupt_reason": None,
        "user_context": request.user_context,
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="0.1.0"
    )


@app.get("/api/v1/smartapply/agents/pdf/{filename}")
async def download_pdf(filename: str = Path(..., description="PDF filename to download")):
    """
    Download a generated PDF recommendation document.
    
    Validates filename to prevent path traversal attacks.
    Returns PDF with proper Content-Type and Content-Disposition headers.
    """
    # Validate filename to prevent path traversal
    # Only allow alphanumeric, underscores, hyphens, and .pdf extension
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+\.pdf$', filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename. Only alphanumeric characters, underscores, hyphens, and .pdf extension allowed."
        )
    
    # Construct safe file path
    pdf_dir = os.getenv("PDF_OUTPUT_DIR", "./output/pdfs")
    file_path = os.path.join(pdf_dir, filename)
    
    # Resolve to absolute path and verify it's within PDF directory
    abs_path = os.path.abspath(file_path)
    abs_pdf_dir = os.path.abspath(pdf_dir)
    
    # Prevent path traversal by ensuring file is within PDF directory
    if not abs_path.startswith(abs_pdf_dir):
        raise HTTPException(
            status_code=403,
            detail="Access denied: Invalid file path"
        )
    
    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"PDF file not found: {filename}"
        )
    
    # Return file with proper headers
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff"
        }
    )


@app.post("/api/v1/smartapply/agents/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with the Smart Apply agent.
    
    The agent will:
    1. Collect user profile (GPA, budget, preferred countries, etc.)
    2. Search for matching schools
    3. Get user approval on selected schools (with interrupts)
    4. Generate PDF recommendation document
    
    Returns conversation history and results.
    """
    try:
        # Run agent
        session_id = request.session_id or f"session_{datetime.utcnow().timestamp()}"
        final_state = run_agent(request.message, session_id=session_id)
        
        # Extract last assistant message
        messages = final_state.get("messages", [])
        last_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                last_message = msg.get("content", "")
                break
        
        # Check if agent requires user input (interrupted state)
        requires_user_input = final_state.get("needs_user_input", False)
        interrupt_reason = final_state.get("interrupt_reason")
        
        # Format response
        response = ChatResponse(
            response=last_message,
            messages=[Message(**msg) for msg in messages],
            current_step=final_state.get("current_step", "unknown"),
            schools_count=len(final_state.get("schools", [])),
            pdf_generated=final_state.get("pdf_generated", False),
            pdf_path=final_state.get("pdf_path"),
            requires_user_input=requires_user_input,
            interrupt_reason=interrupt_reason
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {str(e)}"
        )


@app.post("/api/v1/smartapply/agents/chat/stream")
async def chat_stream(body: ChatRequest, http_request: Request):
    """
    Chat with true streaming response (SSE).
    
    Returns agent thoughts and actions in real-time using EventSourceResponse.
    Handles human-in-the-loop interrupts properly.
    """
    async def event_generator(req: Request) -> AsyncGenerator[str, None]:
        """Generate SSE events with proper async streaming."""
        try:
            session_id = body.session_id or f"session_{datetime.utcnow().timestamp()}"
            config = {"configurable": {"thread_id": session_id}}

            # Check if we're resuming from an interrupt (user_response provided)
            if body.user_response:
                current_state = agent_graph.get_state(config)
                if current_state.next:
                    logger.info(f"Resuming stream from interrupt at node: {current_state.next}")
                    # Update state with user feedback
                    agent_graph.update_state(config, {
                        "user_feedback": body.user_response,
                        "needs_user_input": False,
                    })
                    # Resume execution with None input (continues from checkpoint)
                    input_state = None
                else:
                    # No interrupt to resume — treat as new conversation
                    input_state = _build_initial_state(body, session_id)
            else:
                # New conversation
                input_state = _build_initial_state(body, session_id)

            agent_started = False

            # Stream the graph execution
            async for event in agent_graph.astream_events(
                input_state,
                config=config,
                version="v1",
                include_names=["profile_collector", "school_finder", "human_approval", "document_generator"]
            ):
                # Check if client disconnected
                if await req.is_disconnected():
                    break
                
                event_type = event.get("event")
                node_name = event.get("name")
                data = event.get("data", {})
                
                if event_type == "on_chain_start":
                    # Only emit agent_start once (first node)
                    if not agent_started:
                        agent_started = True
                        yield json.dumps({'type': 'agent_start', 'timestamp': datetime.utcnow().isoformat()})
                
                elif event_type == "on_chain_stream":
                    # Node is processing
                    if node_name and data:
                        node_output = data.get("output", {})
                        messages = node_output.get("messages", [])
                        
                        # Stream new messages
                        for msg in messages:
                            if isinstance(msg, dict):
                                event_data = {
                                    "type": "message",
                                    "role": msg.get("role"),
                                    "content": msg.get("content"),
                                    "timestamp": msg.get("timestamp"),
                                    "node": node_name
                                }
                                yield json.dumps(event_data)
                            
                            # Small delay to simulate real-time processing
                            await asyncio.sleep(0.05)
                
                elif event_type == "on_chain_end":
                    # Node completed
                    final_output = event.get("data", {}).get("output", {})
                    current_step = final_output.get("current_step")
                    needs_input = final_output.get("needs_user_input", False)
                    interrupt_reason = final_output.get("interrupt_reason")
                    
                    # Check if we hit a human approval interrupt
                    if needs_input and interrupt_reason:
                        event_data = {
                            "type": "interrupt",
                            "reason": interrupt_reason,
                            "current_step": current_step,
                            "requires_user_input": True
                        }
                        yield json.dumps(event_data)
                        break
                    
                    # Check if profile collection needs more input (graph ended at END via ask_question)
                    if needs_input and not interrupt_reason:
                        # Extract last assistant message from the node output
                        output_messages = final_output.get("messages", [])
                        last_content = ""
                        for msg in reversed(output_messages):
                            if isinstance(msg, dict) and msg.get("role") == "assistant":
                                last_content = msg.get("content", "")
                                break
                        
                        event_data = {
                            "type": "message",
                            "role": "assistant",
                            "content": last_content,
                            "current_step": current_step,
                            "needs_user_input": True,
                            "requires_user_input": True
                        }
                        yield json.dumps(event_data)
                        break
                    
                    # Check if complete
                    if current_step == "complete":
                        event_data = {
                            "type": "complete",
                            "current_step": current_step,
                            "schools_count": len(final_output.get("schools", [])),
                            "pdf_generated": final_output.get("pdf_generated", False),
                            "pdf_path": final_output.get("pdf_path")
                        }
                        yield json.dumps(event_data)
                        break
                    
                    # Graph ended normally (not complete, not needs_input) — emit final state
                    if current_step:
                        event_data = {
                            "type": "state_update",
                            "current_step": current_step,
                            "needs_user_input": needs_input,
                            "schools_count": len(final_output.get("schools", [])),
                            "pdf_generated": final_output.get("pdf_generated", False),
                            "pdf_path": final_output.get("pdf_path")
                        }
                        yield json.dumps(event_data)
                        break
                
                # Yield keepalive ping every few events
                if event_type in ["on_chain_stream"]:
                    yield ": ping\n\n"
            
            # Final completion event if not already sent
            yield json.dumps({'type': 'stream_end', 'timestamp': datetime.utcnow().isoformat()})
            
        except asyncio.CancelledError:
            logger.info("Stream cancelled by client")
            yield json.dumps({'type': 'cancelled', 'message': 'Stream cancelled by client'})
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            event_data = {
                "type": "error",
                "message": str(e)
            }
            yield json.dumps(event_data)
    
    return EventSourceResponse(
        event_generator(http_request),
        media_type="text/event-stream",
        ping=30,  # Send ping every 30 seconds
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
    )


@app.post("/api/v1/agents/chat", response_model=ChatAgentResponse)
async def chat_agent(request: ChatAgentRequest):
    """
    Chat with the supervisor agent — intent classification and sub-agent routing.

    The agent will:
    1. Classify user intent (smart_apply, rcic, services, unclear)
    2. Route to the appropriate sub-agent
    3. Return the sub-agent response or a clarifying question

    Multi-turn support:
    - Detects when the previous turn set needs_user_input=True (Smart Apply paused)
    - On resume, skips intent classification and routes directly to call_smart_apply
    - Extracts user response and forwards it via user_context for Smart Apply

    User context from Go JWT middleware (user_id, preferences) can be
    forwarded via user_context for personalized routing.
    """
    try:
        session_id = request.session_id or f"agent_session_{datetime.utcnow().timestamp()}"
        config = {"configurable": {"thread_id": session_id}}

        # ── Session resume detection ─────────────────────────────────────
        # Check if a previous turn paused with needs_user_input=True
        is_resume_turn = False
        user_context = dict(request.user_context) if request.user_context else {}

        try:
            previous_state = chat_agent_graph.get_state(config)
            state_values = previous_state.values if previous_state.values else {}
            if state_values.get("needs_user_input"):
                is_resume_turn = True
                logger.info(
                    f"chat_agent: resume turn detected for session_id={session_id!r}, "
                    f"previous_step={state_values.get('current_step')!r}"
                )
        except Exception:
            # No previous state (first turn) — proceed normally
            pass

        # Build initial ChatAgentState
        messages = [
            {"role": "user", "content": request.message, "timestamp": datetime.utcnow().isoformat()}
        ]

        if is_resume_turn:
            # Resume: skip intent classification, route directly to Smart Apply
            # Extract user response (last user message) and forward via user_context
            initial_state = {
                "messages": messages,
                "intent": "smart_apply",
                "sub_agent_response": None,
                "user_context": user_context,
                "user_response": request.message,
                "error_message": None,
                "session_id": session_id,
                "current_step": "start",
            }
            logger.info(
                f"chat_agent: routing directly to smart_apply, "
                f"user_response={request.message[:80]!r}"
            )
        else:
            # New turn: normal behavior — classify intent first
            initial_state = {
                "messages": messages,
                "intent": None,
                "sub_agent_response": None,
                "user_context": user_context,
                "error_message": None,
                "session_id": session_id,
                "current_step": "start",
            }

        # Invoke the compiled graph
        final_state = chat_agent_graph.invoke(initial_state, config=config)

        # Extract the assistant's last message from conversation history
        all_messages = final_state.get("messages", [])
        last_assistant_msg = ""
        for msg in reversed(all_messages):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                last_assistant_msg = msg.get("content", "")
                break

        # Build structured response
        response = ChatAgentResponse(
            intent=final_state.get("intent"),
            response=last_assistant_msg,
            messages=[Message(**msg) for msg in all_messages if isinstance(msg, dict)],
            sub_agent_response=final_state.get("sub_agent_response"),
            error_message=final_state.get("error_message"),
            current_step=final_state.get("current_step"),
            session_id=session_id,
            needs_user_input=final_state.get("needs_user_input"),
            interrupt_reason=_extract_interrupt_reason(final_state),
        )

        logger.info(
            f"chat_agent: intent={response.intent}, "
            f"current_step={response.current_step}, "
            f"session_id={session_id!r}, "
            f"needs_user_input={response.needs_user_input}"
        )

        return response

    except Exception as e:
        logger.error(f"chat_agent endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Chat agent error: {str(e)}"
        )


@app.post("/api/v1/agents/chat/stream")
async def chat_agent_stream(request: ChatAgentRequest, http_request: Request):
    """
    Chat with the supervisor agent via streaming SSE.

    Emits structured events as the graph executes:
    - intent_classified: intent classification result
    - sub_agent_start: sub-agent invocation beginning
    - sub_agent_end: sub-agent invocation complete
    - message: assistant message content
    - stub_response: stub sub-agent response (services/rcic coming soon)
    - clarification: clarifying question for unclear intent
    - stream_end: all events complete

    Uses chat_agent_graph.astream_events() under the hood.
    """
    async def event_generator(req: Request) -> AsyncGenerator[dict, None]:
        try:
            session_id = request.session_id or f"agent_stream_{datetime.utcnow().timestamp()}"
            config = {"configurable": {"thread_id": session_id}}

            # ── Session resume detection ─────────────────────────────────────
            is_resume_turn = False
            user_context = dict(request.user_context) if request.user_context else {}

            try:
                previous_state = chat_agent_graph.get_state(config)
                state_values = previous_state.values if previous_state.values else {}
                if state_values.get("needs_user_input"):
                    is_resume_turn = True
                    logger.info(
                        f"chat_agent_stream: resume turn for session_id={session_id!r}"
                    )
            except Exception:
                pass

            # Build initial state
            messages = [
                {"role": "user", "content": request.message, "timestamp": datetime.utcnow().isoformat()}
            ]

            if is_resume_turn:
                initial_state = {
                    "messages": messages,
                    "intent": "smart_apply",
                    "sub_agent_response": None,
                    "user_context": user_context,
                    "user_response": request.message,
                    "error_message": None,
                    "session_id": session_id,
                    "current_step": "start",
                }
            else:
                initial_state = {
                    "messages": messages,
                    "intent": None,
                    "sub_agent_response": None,
                    "user_context": user_context,
                    "error_message": None,
                    "session_id": session_id,
                    "current_step": "start",
                }

            # Track which sub-agents have started for dedup
            seen_nodes = set()

            # Stream graph events
            async for event in chat_agent_graph.astream_events(
                initial_state,
                config=config,
                version="v2",
            ):
                if await req.is_disconnected():
                    logger.info("chat_agent_stream: client disconnected")
                    break

                event_type = event.get("event")
                name = event.get("name", "")
                data = event.get("data", {})

                # ── on_chain_start: detect sub-agent invocations ──
                if event_type == "on_chain_start":
                    sub_agent_map = {
                        "classify_intent": "classify_intent",
                        "call_smart_apply": "smart_apply",
                        "call_services_stub": "services_stub",
                        "call_rcic_stub": "rcic_stub",
                        "ask_clarification": "clarification",
                        "relay_question": "relay_question",
                        "handle_sub_agent_error": "error_handler",
                    }
                    if name in sub_agent_map and name not in seen_nodes:
                        seen_nodes.add(name)
                        yield {
                            "event_type": "sub_agent_start",
                            "data": {
                                "node": name,
                                "agent": sub_agent_map[name],
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                        }

                # ── on_chain_end: emit sub-agent results ──
                elif event_type == "on_chain_end":
                    output = data.get("output", {}) or {}

                    sub_agent_map = {
                        "classify_intent": "classify_intent",
                        "call_smart_apply": "smart_apply",
                        "call_services_stub": "services_stub",
                        "call_rcic_stub": "rcic_stub",
                        "ask_clarification": "clarification",
                        "relay_question": "relay_question",
                        "handle_sub_agent_error": "error_handler",
                    }

                    if name == "classify_intent" and name in seen_nodes:
                        yield {
                            "event_type": "intent_classified",
                            "data": {
                                "intent": output.get("intent"),
                                "current_step": output.get("current_step"),
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                        }

                    elif name in ("call_services_stub", "call_rcic_stub") and name in seen_nodes:
                        sub_resp = output.get("sub_agent_response", {})
                        yield {
                            "event_type": "stub_response",
                            "data": {
                                "agent": sub_agent_map[name],
                                "message": sub_resp.get("message", ""),
                                "available_alternatives": sub_resp.get("available_alternatives", []),
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        yield {
                            "event_type": "sub_agent_end",
                            "data": {"node": name, "agent": sub_agent_map[name]},
                            "timestamp": datetime.utcnow().isoformat(),
                        }

                    elif name == "call_smart_apply" and name in seen_nodes:
                        for msg in output.get("messages", []):
                            if isinstance(msg, dict) and msg.get("role") == "assistant":
                                yield {
                                    "event_type": "message",
                                    "data": {
                                        "role": "assistant",
                                        "content": msg.get("content", ""),
                                    },
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                        sub_resp = output.get("sub_agent_response", {})
                        if sub_resp.get("requires_user_input"):
                            yield {
                                "event_type": "message",
                                "data": {
                                    "role": "assistant",
                                    "content": sub_resp.get("response", ""),
                                    "requires_user_input": True,
                                    "interrupt_reason": sub_resp.get("interrupt_reason"),
                                },
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        yield {
                            "event_type": "sub_agent_end",
                            "data": {"node": name, "agent": "smart_apply"},
                            "timestamp": datetime.utcnow().isoformat(),
                        }

                    elif name == "ask_clarification" and name in seen_nodes:
                        for msg in output.get("messages", []):
                            if isinstance(msg, dict) and msg.get("role") == "assistant":
                                yield {
                                    "event_type": "clarification",
                                    "data": {"content": msg.get("content", "")},
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                        yield {
                            "event_type": "sub_agent_end",
                            "data": {"node": name, "agent": "clarification"},
                            "timestamp": datetime.utcnow().isoformat(),
                        }

                    elif name == "relay_question" and name in seen_nodes:
                        for msg in output.get("messages", []):
                            if isinstance(msg, dict) and msg.get("role") == "assistant":
                                yield {
                                    "event_type": "message",
                                    "data": {
                                        "role": "assistant",
                                        "content": msg.get("content", ""),
                                        "requires_user_input": True,
                                    },
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                        yield {
                            "event_type": "sub_agent_end",
                            "data": {"node": name, "agent": "relay_question"},
                            "timestamp": datetime.utcnow().isoformat(),
                        }

                    elif name == "handle_sub_agent_error" and name in seen_nodes:
                        for msg in output.get("messages", []):
                            if isinstance(msg, dict) and msg.get("role") == "assistant":
                                yield {
                                    "event_type": "message",
                                    "data": {
                                        "role": "assistant",
                                        "content": msg.get("content", ""),
                                        "is_error": True,
                                    },
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                        yield {
                            "event_type": "sub_agent_end",
                            "data": {"node": name, "agent": "error_handler"},
                            "timestamp": datetime.utcnow().isoformat(),
                        }

            # Final event
            yield {
                "event_type": "stream_end",
                "data": {"session_id": session_id},
                "timestamp": datetime.utcnow().isoformat(),
            }

        except asyncio.CancelledError:
            logger.info("chat_agent_stream: cancelled")
            yield {
                "event_type": "error",
                "data": {"message": "Stream cancelled"},
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"chat_agent_stream error: {e}")
            yield {
                "event_type": "error",
                "data": {"message": str(e)},
                "timestamp": datetime.utcnow().isoformat(),
            }

    return EventSourceResponse(
        event_generator(http_request),
        media_type="text/event-stream",
        ping=30,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _extract_interrupt_reason(state: dict) -> Optional[str]:
    """Extract interrupt_reason from sub_agent_response in state."""
    sub_agent_response = state.get("sub_agent_response")
    if sub_agent_response and isinstance(sub_agent_response, dict):
        return sub_agent_response.get("interrupt_reason")
    return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=18000,
        reload=True,
        log_level="info",
    )
