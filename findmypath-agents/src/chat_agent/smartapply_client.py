"""
Smart Apply HTTP client for the Chat Agent supervisor graph.

Provides an async HTTP client that calls the Go backend Smart Apply chat
endpoint (POST /api/v1/smartapply/agents/chat) with retry, timeout, and
structured observability.

Usage:
    client = SmartApplyClient()
    result = await client.chat(
        message="I want to find schools in Canada",
        session_id="sess_123",
        user_context={"user_id": "u-456"}
    )

    # Or via async context manager:
    async with SmartApplyClient() as client:
        result = await client.chat(message="...", session_id="...")
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)


class SmartApplyClient:
    """
    Async HTTP client for the Smart Apply sub-agent chat endpoint.

    Calls POST /api/v1/smartapply/agents/chat on the Go backend with:
    - 30-second total timeout
    - 3 retries with exponential backoff (0.5s, 1s, 2s)
    - Structured INFO-level request logging (endpoint + session_id)
    - WARNING-level failure logging with retry count
    - Returns a structured response dict or None on failure

    The client lazily creates an httpx.AsyncClient on first use and
    reuses it across calls. Use as an async context manager for
    explicit lifecycle management (recommended for long-running processes).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize the Smart Apply HTTP client.

        Args:
            base_url: Go backend base URL (default: GO_BACKEND_URL env var
                      or http://localhost:8080)
            timeout: Total request timeout in seconds (default: 30)
            max_retries: Maximum retry attempts for transient failures
                         (default: 3)
        """
        self.base_url = (
            base_url or os.getenv("GO_BACKEND_URL", "http://localhost:8080")
        ).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "SmartApplyClient":
        """Async context manager entry — ensures client is initialized."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit — closes the underlying client."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the httpx.AsyncClient if not already created."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Explicitly close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        message: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call the Smart Apply sub-agent chat endpoint.

        POSTs to {base_url}/api/v1/smartapply/agents/chat with the user
        message, session ID, and optional user context forwarded from the
        Go JWT middleware.

        Args:
            message: The user's chat message text.
            session_id: Unique session identifier for conversation continuity.
            user_context: Optional context dict from the Go middleware
                          (user_id, preferences, etc.). Only user_id is
                          logged — never PII like email or name.

        Returns:
            A dict with the parsed ChatResponse fields on success:
                {
                    "response": str,          # Assistant's reply text
                    "messages": list[dict],   # Full conversation history
                    "current_step": str,      # Agent step indicator
                    "schools_count": int,
                    "pdf_generated": bool,
                    "pdf_path": str | None,
                    "requires_user_input": bool,
                    "interrupt_reason": str | None,
                }
            On failure, returns a structured error dict with error_type:
                {
                    "response": "",
                    "messages": [],
                    "current_step": "error",
                    "error_message": str,
                    "error_type": str,        # "timeout" | "connection" | "server_error" | "not_found" | "bad_request" | "unknown"
                    "schools_count": 0,
                    "pdf_generated": False,
                    "pdf_path": None,
                    "requires_user_input": False,
                    "interrupt_reason": None,
                }
        """
        endpoint = "/api/v1/smartapply/agents/chat"
        url = f"{self.base_url}{endpoint}"

        # Only log safe identifiers — never PII
        safe_user_id = "anonymous"
        if user_context:
            safe_user_id = str(user_context.get("user_id", "anonymous"))

        logger.info(
            f"SmartApplyClient.chat: POST {endpoint} "
            f"session_id={session_id!r} user_id={safe_user_id}"
        )

        payload: Dict[str, Any] = {
            "message": message,
            "session_id": session_id,
        }
        # Forward user_context (user_id, email, name, timezone) to Go backend
        if user_context:
            payload["user_context"] = {
                "user_id": user_context.get("user_id"),
                "email": user_context.get("email"),
                "name": user_context.get("name"),
                "timezone": user_context.get("timezone"),
            }
            # Also forward user_response if present (human-in-the-loop resume)
            if "user_response" in user_context:
                payload["user_context"]["user_response"] = user_context["user_response"]

        client = await self._ensure_client()

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                response = await client.post(url, json=payload)

                logger.debug(
                    f"Smart Apply API response: status={response.status_code} "
                    f"attempt={attempt + 1}/{self.max_retries}"
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"Smart Apply chat success: "
                        f"session_id={session_id!r} "
                        f"current_step={data.get('current_step', 'unknown')} "
                        f"schools_count={data.get('schools_count', 0)}"
                    )
                    return data

                elif response.status_code >= 500:
                    # Server error — retry with backoff
                    error_text = response.text[:200]
                    logger.warning(
                        f"Smart Apply API server error: status={response.status_code} "
                        f"attempt={attempt + 1}/{self.max_retries} "
                        f"body={error_text!r}"
                    )
                    last_error = ValueError(
                        f"Server error {response.status_code}: {error_text}"
                    )
                    if attempt < self.max_retries - 1:
                        backoff = 0.5 * (2 ** attempt)
                        await asyncio.sleep(backoff)
                        continue
                    break

                elif response.status_code == 400:
                    # Client error — do not retry
                    error_text = response.text[:200]
                    logger.warning(
                        f"Smart Apply API bad request: {error_text!r}"
                    )
                    return {
                        "response": "",
                        "messages": [],
                        "current_step": "error",
                        "error_message": f"Bad request: {error_text}",
                        "schools_count": 0,
                        "pdf_generated": False,
                        "pdf_path": None,
                        "requires_user_input": False,
                        "interrupt_reason": None,
                    }

                elif response.status_code == 404:
                    logger.warning(f"Smart Apply API endpoint not found: {url}")
                    return _error_dict(
                        error_type="not_found",
                        error_message="The Smart Apply service endpoint was not found. Please check the backend configuration.",
                    )

                else:
                    # Other client errors — do not retry
                    error_text = response.text[:200]
                    logger.warning(
                        f"Smart Apply API client error: status={response.status_code} "
                        f"body={error_text!r}"
                    )
                    return _error_dict(
                        error_type="unknown",
                        error_message=f"Unexpected error (HTTP {response.status_code}): {error_text}",
                    )

            except httpx.TimeoutException:
                logger.warning(
                    f"Smart Apply API timeout (attempt {attempt + 1}/{self.max_retries}): "
                    f"{url}"
                )
                last_error = httpx.TimeoutException("Request timed out")
                if attempt < self.max_retries - 1:
                    backoff = 0.5 * (2 ** attempt)
                    await asyncio.sleep(backoff)

            except httpx.RequestError as exc:
                logger.warning(
                    f"Smart Apply API request error (attempt {attempt + 1}/{self.max_retries}): "
                    f"{exc}"
                )
                last_error = exc
                # Network errors may be transient — retry
                if attempt < self.max_retries - 1:
                    backoff = 0.5 * (2 ** attempt)
                    await asyncio.sleep(backoff)
                else:
                    break

            except Exception as exc:
                # Unexpected error — log and return structured error
                logger.error(
                    f"Smart Apply chat unexpected error: {exc}"
                )
                return _error_dict(
                    error_type="unknown",
                    error_message=f"An unexpected error occurred: {exc}",
                )

        # All retries exhausted — classify the error type from last_error
        error_type = _classify_error_type(last_error)
        user_message = _error_user_message(error_type, last_error)

        logger.error(
            f"Smart Apply chat failed after {self.max_retries} retries: "
            f"session_id={session_id!r} last_error={last_error} error_type={error_type}"
        )
        return _error_dict(error_type=error_type, error_message=user_message)


# ── Error classification helpers ─────────────────────────────────────────────

def _error_dict(error_type: str, error_message: str) -> Dict[str, Any]:
    """Build a structured error response dict with error_type."""
    return {
        "response": "",
        "messages": [],
        "current_step": "error",
        "error_message": error_message,
        "error_type": error_type,
        "schools_count": 0,
        "pdf_generated": False,
        "pdf_path": None,
        "requires_user_input": False,
        "interrupt_reason": None,
    }


def _classify_error_type(error: Optional[Exception]) -> str:
    """Classify an exception into a user-facing error_type category."""
    if error is None:
        return "unknown"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.ConnectError):
        return "connection"
    if isinstance(error, httpx.RequestError):
        return "connection"
    if isinstance(error, ValueError) and "Server error 5" in str(error):
        return "server_error"
    return "unknown"


def _error_user_message(error_type: str, error: Optional[Exception]) -> str:
    """Generate a user-friendly error message for the given error type."""
    messages = {
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
            "The Smart Apply service endpoint was not found. "
            "Please check the backend configuration."
        ),
        "bad_request": (
            "Your request could not be processed. Please check your input and try again."
        ),
        "unknown": (
            "An unexpected error occurred while processing your request. "
            "Please try again."
        ),
    }
    return messages.get(error_type, messages["unknown"])
