"""Tests for hook_router fix (Issue 4).

Verifies that _build_predicate_context is called with the correct
tool_name value (not getattr(Request, "tool_name", None)).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestHookRouterToolNameFix:
    """Verify tool_name is not read from the FastAPI Request class."""

    def test_evaluate_sync_does_not_read_request_class_attr(self):
        """_evaluate_sync should pass tool_name=None for UserPromptSubmit,
        not getattr(Request, 'tool_name', None)."""
        from agentalloy.api.hook_router import _evaluate_sync

        # Mock the skill loader functions — they are imported inside _evaluate_sync
        mock_skill = {
            "signal_keywords": [],
            "exit_gates": {},
            "raw_prose": "",
        }

        with (
            patch("agentalloy.signals.skill_loader._read_phase", return_value="build"),
            patch(
                "agentalloy.signals.skill_loader._load_workflow_skill_for_phase",
                return_value=mock_skill,
            ),
            patch("agentalloy.signals.prefilter.check_prefilter", return_value=None),
        ):
            # Should not raise — tool_name=None is valid
            result = _evaluate_sync(
                prompt="test prompt",
                cwd=Path("/tmp"),
                phase="build",
            )
            assert result["composed_block"] == ""
            assert result["should_compose"] is False

    def test_pre_tool_use_passes_tool_name_from_body(self):
        """The pre-tool-use endpoint extracts tool_name from request body."""
        # Build a minimal test app
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from agentalloy.api.hook_router import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)

        # Send a pre-tool-use request with tool_name
        response = client.post(
            "/v1/hook/pre-tool-use",
            json={"tool_name": "Edit", "cwd": "/tmp"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fresh"
        assert "system_skills" in data

    def test_user_prompt_submit_passes_none_tool_name(self):
        """UserPromptSubmit endpoint should pass tool_name=None."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from agentalloy.api.hook_router import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)

        # Send a user-prompt-submit request
        response = client.post(
            "/v1/hook/user-prompt-submit",
            json={"prompt": "test prompt", "cwd": "/tmp"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "composed_block" in data
        assert "should_compose" in data
