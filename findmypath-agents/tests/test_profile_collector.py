"""
Tests for profile_collector node in Smart Apply agent.

Tests verify:
- Pre-population from user_context (email, name)
- Skipping questions for pre-populated fields
- Backward compatibility without user_context
- Logging behavior (only user_id, not email)
"""

import pytest
import logging
from unittest.mock import patch
from src.graph.nodes import profile_collector


def _make_state(
    user_profile=None,
    user_context=None,
    messages=None,
):
    """Helper to build a minimal AgentState dict for testing."""
    return {
        "messages": messages or [],
        "user_profile": user_profile or {},
        "schools": [],
        "selected_schools": [],
        "pdf_path": None,
        "pdf_generated": False,
        "current_step": "collecting_profile",
        "needs_user_input": False,
        "user_feedback": None,
        "session_id": "test-session",
        "created_at": None,
        "updated_at": None,
        "user_context": user_context,
    }


class TestProfileCollectorWithoutUserContext:
    """Tests for backward compatibility — no user_context provided."""

    def test_asks_for_name_first(self):
        """When no user_context, should ask for name as first missing field."""
        state = _make_state()
        result = profile_collector(state)

        assert result["needs_user_input"] is True
        assert result["current_step"] == "collecting_profile"
        assert len(result["messages"]) == 1
        assert "Bạn tên gì?" in result["messages"][0]["content"]

    def test_asks_for_email_when_name_present(self):
        """When name already in profile but no user_context, asks for email."""
        state = _make_state(user_profile={"name": "Test User"})
        result = profile_collector(state)

        assert result["needs_user_input"] is True
        assert "Email của bạn là gì?" in result["messages"][0]["content"]

    def test_profile_complete(self):
        """When all required fields are present, marks profile_complete."""
        full_profile = {
            "name": "Test",
            "email": "test@example.com",
            "gpa": 3.5,
            "budget": 30000,
            "preferred_countries": ["USA"],
            "major": "CS",
        }
        state = _make_state(user_profile=full_profile)
        result = profile_collector(state)

        assert result["current_step"] == "profile_complete"
        assert result.get("needs_user_input") is None or result.get("needs_user_input") is False


class TestProfileCollectorWithUserContext:
    """Tests for pre-population from user_context."""

    def test_prepopulates_email_from_user_context(self):
        """When user_context.email is present, it should be pre-populated."""
        state = _make_state(
            user_context={"user_id": "u1", "email": "jwt@example.com", "name": "JWT User"},
        )
        result = profile_collector(state)

        # Email and name should be pre-populated
        profile = result["user_profile"]
        assert profile["email"] == "jwt@example.com"
        assert profile["name"] == "JWT User"

        # Should skip to the next missing field (gpa)
        assert result["needs_user_input"] is True
        assert "GPA" in result["messages"][0]["content"]

    def test_skips_email_question_when_in_user_context(self):
        """Profile collector should NOT ask for email when user_context.email exists."""
        state = _make_state(
            user_context={"user_id": "u2", "email": "skip@test.com"},
        )
        result = profile_collector(state)

        # First question should NOT be about email
        question = result["messages"][0]["content"]
        assert "Email" not in question
        # Should ask for name (which is NOT in user_context)
        assert "Bạn tên gì?" in question

    def test_skips_name_question_when_in_user_context(self):
        """Profile collector should NOT ask for name when user_context.name exists."""
        state = _make_state(
            user_context={"user_id": "u3", "name": "Pre-filled Name"},
        )
        result = profile_collector(state)

        profile = result["user_profile"]
        assert profile["name"] == "Pre-filled Name"
        # Should ask for email (not in user_context)
        assert "Email" in result["messages"][0]["content"]

    def test_skips_both_name_and_email_when_both_in_context(self):
        """When both name and email are in user_context, skip to gpa."""
        state = _make_state(
            user_context={
                "user_id": "u4",
                "email": "both@test.com",
                "name": "Both Name",
            },
        )
        result = profile_collector(state)

        profile = result["user_profile"]
        assert profile["email"] == "both@test.com"
        assert profile["name"] == "Both Name"
        # First question should be about GPA
        assert "GPA" in result["messages"][0]["content"]

    def test_does_not_override_existing_profile_fields(self):
        """If user_profile already has a field, user_context should not overwrite it."""
        state = _make_state(
            user_profile={"name": "Existing Name"},
            user_context={"user_id": "u5", "name": "JWT Name", "email": "jwt@test.com"},
        )
        result = profile_collector(state)

        # Existing name should be preserved
        assert result["user_profile"]["name"] == "Existing Name"
        # Email should still be pre-populated (was not in profile)
        assert result["user_profile"]["email"] == "jwt@test.com"

    def test_empty_user_context_string_not_prepopulated(self):
        """Empty string values in user_context should not pre-populate."""
        state = _make_state(
            user_context={"user_id": "u6", "email": "", "name": ""},
        )
        result = profile_collector(state)

        # Empty strings should not populate
        assert "email" not in result["user_profile"]
        assert "name" not in result["user_profile"]
        # Should still ask for name first
        assert "Bạn tên gì?" in result["messages"][0]["content"]


class TestProfileCollectorLogging:
    """Tests for logging behavior — only user_id should be logged."""

    def test_logs_prepopulation_with_user_id(self):
        """When fields are pre-populated, log should contain user_id."""
        state = _make_state(
            user_context={"user_id": "logged-user-1", "email": "log@test.com"},
        )
        with patch("src.graph.nodes.logger") as mock_logger:
            profile_collector(state)

        # Find the info log call about pre-population
        calls = [str(c) for c in mock_logger.info.call_args_list]
        prepop_log = [c for c in calls if "pre-populated" in c]
        assert len(prepop_log) == 1
        assert "logged-user-1" in prepop_log[0]

    def test_does_not_log_email_value(self):
        """Email value should never appear in log messages."""
        state = _make_state(
            user_context={"user_id": "u7", "email": "secret@private.com", "name": "Secret"},
        )
        with patch("src.graph.nodes.logger") as mock_logger:
            profile_collector(state)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        for call in calls:
            assert "secret@private.com" not in call

    def test_logs_no_prepopulation_when_no_user_context(self):
        """When no user_context, log should indicate no pre-population."""
        state = _make_state()
        with patch("src.graph.nodes.logger") as mock_logger:
            profile_collector(state)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        no_prepop_log = [c for c in calls if "no pre-populated" in c]
        assert len(no_prepop_log) == 1


class TestProfileCollectorEdgeCases:
    """Edge case tests."""

    def test_user_context_with_only_user_id(self):
        """user_context with only user_id should not pre-populate anything."""
        state = _make_state(
            user_context={"user_id": "u8"},
        )
        result = profile_collector(state)

        # No pre-population
        assert result["user_profile"] == {}
        # Should ask for name first
        assert "Bạn tên gì?" in result["messages"][0]["content"]

    def test_user_context_is_none(self):
        """Explicit None user_context should work the same as missing key."""
        state = _make_state(user_context=None)
        result = profile_collector(state)

        assert result["user_profile"] == {}
        assert "Bạn tên gì?" in result["messages"][0]["content"]

    def test_partial_profile_with_user_context(self):
        """Pre-populate only the missing fields when profile is partially filled."""
        state = _make_state(
            user_profile={"gpa": 3.8},
            user_context={"user_id": "u9", "email": "partial@test.com", "name": "Partial"},
        )
        result = profile_collector(state)

        profile = result["user_profile"]
        assert profile["gpa"] == 3.8
        assert profile["email"] == "partial@test.com"
        assert profile["name"] == "Partial"
        # Should ask for budget (next missing after name/email/gpa)
        assert "Ngân sách" in result["messages"][0]["content"]
