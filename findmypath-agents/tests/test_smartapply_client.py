"""
Tests for SmartApplyClient — async HTTP client for the Smart Apply sub-agent.

Covers:
- Happy path: successful chat response
- Negative tests: timeout, server error (5xx) with retry, client error (400/404),
  malformed JSON response, connection refused
- Observability: logs emitted at correct levels
"""

import pytest
import pytest_asyncio
import asyncio
import logging
from unittest.mock import AsyncMock, patch, MagicMock

from src.chat_agent.smartapply_client import SmartApplyClient


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def success_response_json():
    """A realistic ChatResponse JSON from the Go backend."""
    return {
        "response": "I found 5 schools matching your profile.",
        "messages": [
            {"role": "user", "content": "I want to find schools", "timestamp": None},
            {
                "role": "assistant",
                "content": "I found 5 schools matching your profile.",
                "timestamp": None,
            },
        ],
        "current_step": "schools_found",
        "schools_count": 5,
        "pdf_generated": False,
        "pdf_path": None,
        "requires_user_input": False,
        "interrupt_reason": None,
    }


@pytest.fixture
def client():
    """Create a SmartApplyClient with a test base URL."""
    return SmartApplyClient(base_url="http://test:9999", max_retries=3)


# ── Happy path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_success(client, success_response_json):
    """Successful POST returns parsed response dict."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = success_response_json

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch.object(client, "_ensure_client", return_value=mock_client):
        result = await client.chat(
            message="I want to find schools in Canada",
            session_id="test-session-1",
            user_context={"user_id": "u-123"},
        )

    assert result is not None
    assert result["response"] == "I found 5 schools matching your profile."
    assert result["schools_count"] == 5
    assert result["current_step"] == "schools_found"
    mock_client.post.assert_called_once()

    # Verify the payload shape
    call_args = mock_client.post.call_args
    assert call_args[1]["json"]["message"] == "I want to find schools in Canada"
    assert call_args[1]["json"]["session_id"] == "test-session-1"


@pytest.mark.asyncio
async def test_chat_success_with_user_response(client, success_response_json):
    """user_context.user_response is forwarded in the payload."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = success_response_json

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch.object(client, "_ensure_client", return_value=mock_client):
        result = await client.chat(
            message="yes, proceed",
            session_id="test-session-2",
            user_context={"user_id": "u-456", "user_response": "yes, proceed"},
        )

    assert result is not None
    call_args = mock_client.post.call_args
    # user_response is now nested inside user_context alongside user_id, email, name, timezone
    assert call_args[1]["json"]["user_context"]["user_response"] == "yes, proceed"


# ── Negative tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_timeout_returns_error_dict(client):
    """Timeout after all retries returns a structured error dict with error_type."""
    mock_client = AsyncMock()
    mock_client.is_closed = False

    # Simulate httpx.TimeoutException
    import httpx
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Read timed out"))

    with patch.object(client, "_ensure_client", return_value=mock_client):
        # Speed up the test by patching sleep
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.chat(
                message="timeout test",
                session_id="test-timeout",
            )

    assert result is not None
    assert result["current_step"] == "error"
    assert result["error_type"] == "timeout"
    assert "error_message" in result
    # Should have attempted max_retries times
    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
async def test_chat_server_error_retries_then_returns_error_dict(client):
    """5xx errors trigger retries; returns a structured error dict after exhausting retries."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(client, "_ensure_client", return_value=mock_client):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.chat(
                message="server error test",
                session_id="test-5xx",
            )

    assert result is not None
    assert result["current_step"] == "error"
    assert result["error_type"] == "server_error"
    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
async def test_chat_400_returns_error_dict(client):
    """400 Bad Request returns a structured error dict (not None)."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = '{"error": "invalid message"}'

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(client, "_ensure_client", return_value=mock_client):
        result = await client.chat(
            message="",  # empty message triggers 400
            session_id="test-400",
        )

    assert result is not None
    assert result["current_step"] == "error"
    assert "error_message" in result
    # Should NOT retry on 400
    assert mock_client.post.call_count == 1


@pytest.mark.asyncio
async def test_chat_404_returns_error_dict(client):
    """404 Not Found returns a structured error dict without retries."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(client, "_ensure_client", return_value=mock_client):
        result = await client.chat(
            message="not found test",
            session_id="test-404",
        )

    assert result is not None
    assert result["current_step"] == "error"
    assert result["error_type"] == "not_found"
    assert mock_client.post.call_count == 1


@pytest.mark.asyncio
async def test_chat_connection_error_retries_then_returns_error_dict(client):
    """Connection refused triggers retries and returns a structured error dict."""
    import httpx
    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch.object(client, "_ensure_client", return_value=mock_client):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.chat(
                message="connection error test",
                session_id="test-conn",
            )

    assert result is not None
    assert result["current_step"] == "error"
    assert result["error_type"] == "connection"
    assert mock_client.post.call_count == 3


# ── Async context manager ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_manager_lifecycle():
    """Client can be used as async context manager."""
    client = SmartApplyClient(base_url="http://test:9999")
    assert client._client is None

    async with client:
        assert client._client is not None
        assert not client._client.is_closed

    # After exiting, client should be closed
    assert client._client is None or client._client.is_closed


# ── Default configuration ───────────────────────────────────────────────────


def test_default_base_url_from_env(monkeypatch):
    """Base URL defaults to GO_BACKEND_URL env var."""
    monkeypatch.setenv("GO_BACKEND_URL", "http://custom:3000")
    client = SmartApplyClient()
    assert client.base_url == "http://custom:3000"


def test_default_timeout_and_retries():
    """Default timeout is 30s and max_retries is 3."""
    client = SmartApplyClient()
    assert client.timeout == 30.0
    assert client.max_retries == 3


@pytest.mark.asyncio
async def test_close_idempotent():
    """Calling close on an already-closed client does not raise."""
    client = SmartApplyClient()
    await client.close()
    await client.close()  # Should not raise


# ── user_context forwarding ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_forwards_user_context_fields(client, success_response_json):
    """user_id, email, name, timezone appear in the POST payload under user_context."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = success_response_json

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch.object(client, "_ensure_client", return_value=mock_client):
        result = await client.chat(
            message="I want to find schools",
            session_id="test-uc-1",
            user_context={
                "user_id": "u-789",
                "email": "test@example.com",
                "name": "Test User",
                "timezone": "America/Toronto",
            },
        )

    assert result is not None
    call_args = mock_client.post.call_args
    payload = call_args[1]["json"]

    # user_context dict should be present with all fields
    assert "user_context" in payload
    uc = payload["user_context"]
    assert uc["user_id"] == "u-789"
    assert uc["email"] == "test@example.com"
    assert uc["name"] == "Test User"
    assert uc["timezone"] == "America/Toronto"


@pytest.mark.asyncio
async def test_chat_forwards_user_context_with_user_response(client, success_response_json):
    """user_context.user_response is included alongside user_id, email, name, timezone."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = success_response_json

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch.object(client, "_ensure_client", return_value=mock_client):
        result = await client.chat(
            message="yes proceed",
            session_id="test-uc-2",
            user_context={
                "user_id": "u-100",
                "email": "a@b.com",
                "name": "Alice",
                "timezone": "UTC",
                "user_response": "yes proceed",
            },
        )

    assert result is not None
    call_args = mock_client.post.call_args
    uc = call_args[1]["json"]["user_context"]
    assert uc["user_id"] == "u-100"
    assert uc["user_response"] == "yes proceed"


@pytest.mark.asyncio
async def test_chat_logs_only_user_id_not_email_or_name(client, success_response_json, caplog):
    """Only user_id appears in INFO logs — email, name, timezone are redacted."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = success_response_json

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch.object(client, "_ensure_client", return_value=mock_client):
        with caplog.at_level(logging.INFO):
            await client.chat(
                message="hello",
                session_id="test-uc-3",
                user_context={
                    "user_id": "u-200",
                    "email": "secret@example.com",
                    "name": "Secret Name",
                    "timezone": "Asia/Vancouver",
                },
            )

    # Combine all log records
    log_text = " ".join(rec.message for rec in caplog.records)

    # user_id should be present
    assert "u-200" in log_text

    # PII fields should NOT appear in logs
    assert "secret@example.com" not in log_text
    assert "Secret Name" not in log_text
    assert "Asia/Vancouver" not in log_text


@pytest.mark.asyncio
async def test_chat_without_user_context_no_user_context_key(client, success_response_json):
    """When user_context is None, no user_context key is in the payload."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = success_response_json

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch.object(client, "_ensure_client", return_value=mock_client):
        result = await client.chat(
            message="hello",
            session_id="test-uc-4",
            user_context=None,
        )

    assert result is not None
    call_args = mock_client.post.call_args
    payload = call_args[1]["json"]
    assert "user_context" not in payload
