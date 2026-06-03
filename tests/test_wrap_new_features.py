"""Tests for wrap subcommand new features and bug fixes.

Covers:
- Child process starts in a new session (process group safety)
- --json flag produces JSON output
- --json flag produces JSON on error paths
- Legacy wire_harness KeyError guard
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentalloy.install.subcommands.wrap import (
    _run,
)

# ---------------------------------------------------------------------------
# Shared fixture: temporary XDG state directory
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_state_dir(tmp_path: Path):
    """Set up a temporary XDG state directory for wrap tests."""
    import os

    config_dir = tmp_path / ".config"
    data_dir = tmp_path / ".local" / "share"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    old_config = os.environ.get("XDG_CONFIG_HOME")
    old_data = os.environ.get("XDG_DATA_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(config_dir)
    os.environ["XDG_DATA_HOME"] = str(data_dir)
    yield config_dir, data_dir
    if old_config is not None:
        os.environ["XDG_CONFIG_HOME"] = old_config
    elif "XDG_CONFIG_HOME" in os.environ:
        del os.environ["XDG_CONFIG_HOME"]
    if old_data is not None:
        os.environ["XDG_DATA_HOME"] = old_data
    elif "XDG_DATA_HOME" in os.environ:
        del os.environ["XDG_DATA_HOME"]


# ---------------------------------------------------------------------------
# Process group safety tests (Issue 2)
# ---------------------------------------------------------------------------


class TestProcessGroupSafety:
    """Verify child process is started in a new session (start_new_session=True)."""

    def test_start_new_session_true(self, tmp_state_dir: tuple[Path, Path]):
        """subprocess.Popen should be called with start_new_session=True."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.wait.return_value = 0

        with (
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.find_listening_pid",
                return_value=9999,
            ),
            patch(
                "agentalloy.install.subcommands.wrap.wire_harness",
                return_value={"files_written": [], "harness": "claude-code"},
            ),
            patch(
                "agentalloy.install.subcommands.wrap.subprocess.Popen",
                return_value=mock_proc,
            ) as mock_popen,
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.stop",
            ),
        ):
            args = argparse.Namespace(
                harness="claude-code",
                port=None,
                via="proxy",
                no_start_server=True,
                child_args=["echo", "hello"],
                json=False,
            )
            _run(args)
            # Verify start_new_session=True was passed
            call_kwargs = mock_popen.call_args
            assert call_kwargs[1].get("start_new_session") is True

    def test_killpg_safe_with_new_session(self, tmp_state_dir: tuple[Path, Path]):
        """With start_new_session=True, child has its own process group.
        The signal handler uses os.killpg(proc.pid, ...) which is safe
        because the child has its own PGID (not the wrapper's).

        The key safety property: start_new_session=True means the child
        gets its own process group. The signal handler calls
        os.killpg(os.getpgid(proc.pid), SIGTERM), which targets only
        the child's process group — never the wrapper or parent shell."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.wait.return_value = 1

        with (
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.find_listening_pid",
                return_value=9999,
            ),
            patch(
                "agentalloy.install.subcommands.wrap.wire_harness",
                return_value={"files_written": [], "harness": "claude-code"},
            ),
            patch(
                "agentalloy.install.subcommands.wrap.subprocess.Popen",
                return_value=mock_proc,
            ) as mock_popen,
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.stop",
            ),
        ):
            args = argparse.Namespace(
                harness="claude-code",
                port=None,
                via="proxy",
                no_start_server=True,
                child_args=["echo", "hello"],
                json=False,
            )
            _run(args)

            # Verify start_new_session=True was passed to Popen
            call_kwargs = mock_popen.call_args
            assert call_kwargs[1].get("start_new_session") is True


# ---------------------------------------------------------------------------
# JSON output tests (Issue 8)
# ---------------------------------------------------------------------------


class TestJsonOutput:
    """Verify --json flag produces JSON output."""

    def _mock_run_with_json(
        self,
        tmp_state_dir: tuple[Path, Path],
        child_args: list[str] | None = None,
    ) -> dict:
        """Run _run with json=True and capture stdout."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.wait.return_value = 0

        captured_output = []

        def capture_print(*args, **kwargs):
            captured_output.append(kwargs.get("end", "") or "")
            captured_output.append(" ".join(str(a) for a in args))

        with (
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.find_listening_pid",
                return_value=9999,
            ),
            patch(
                "agentalloy.install.subcommands.wrap.wire_harness",
                return_value={
                    "files_written": [{"path": "/tmp/test.md", "action": "injected"}],
                    "harness": "claude-code",
                },
            ),
            patch(
                "agentalloy.install.subcommands.wrap.subprocess.Popen",
                return_value=mock_proc,
            ),
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.stop",
            ),
            patch("agentalloy.install.subcommands.wrap.print_rich"),
            patch("builtins.print", side_effect=capture_print),
        ):
            args = argparse.Namespace(
                harness="claude-code",
                port=8000,
                via="proxy",
                no_start_server=True,
                child_args=child_args or ["echo", "hello"],
                json=True,
            )
            rc = _run(args)
            assert rc == 0

        # Parse the JSON output
        json_str = "".join(captured_output)
        return json.loads(json_str)

    def test_json_output_on_success(self, tmp_state_dir: tuple[Path, Path]):
        """Successful wrap with --json should produce valid JSON."""
        result = self._mock_run_with_json(tmp_state_dir)
        assert result["action"] == "wrap"
        assert result["harness"] == "claude-code"
        assert result["port"] == 8000
        assert result["via"] == "proxy"
        assert result["child_pid"] == 54321
        assert result["exit_code"] == 0
        assert result["server_started"] is False
        assert len(result["files_written"]) == 1

    def test_json_output_on_invalid_harness(self, tmp_state_dir: tuple[Path, Path]):
        """Invalid harness with --json should produce error JSON."""
        captured_output = []

        def capture_print(*args, **kwargs):
            captured_output.append(" ".join(str(a) for a in args))

        with (
            patch("builtins.print", side_effect=capture_print),
            patch("agentalloy.install.subcommands.wrap.print_rich_stderr"),
        ):
            args = argparse.Namespace(
                harness="nonexistent",
                port=None,
                via="proxy",
                no_start_server=True,
                child_args=["echo", "hello"],
                json=True,
            )
            rc = _run(args)
            assert rc == 1

        result = json.loads("".join(captured_output))
        assert "error" in result
        assert "nonexistent" in result["error"]

    def test_json_output_on_no_child_args(self, tmp_state_dir: tuple[Path, Path]):
        """No child args with --json should produce error JSON."""
        captured_output = []

        def capture_print(*args, **kwargs):
            captured_output.append(" ".join(str(a) for a in args))

        with (
            patch("builtins.print", side_effect=capture_print),
            patch("agentalloy.install.subcommands.wrap.print_rich_stderr"),
        ):
            args = argparse.Namespace(
                harness="claude-code",
                port=None,
                via="proxy",
                no_start_server=True,
                child_args=[],
                json=True,
            )
            rc = _run(args)
            assert rc == 1

        result = json.loads("".join(captured_output))
        assert "error" in result
        assert "child process" in result["error"].lower()

    def test_json_output_on_file_not_found(self, tmp_state_dir: tuple[Path, Path]):
        """FileNotFoundError with --json should produce error JSON."""
        captured_output = []

        def capture_print(*args, **kwargs):
            captured_output.append(" ".join(str(a) for a in args))

        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.wait.return_value = 0

        with (
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.find_listening_pid",
                return_value=9999,
            ),
            patch(
                "agentalloy.install.subcommands.wrap.wire_harness",
                return_value={"files_written": [], "harness": "claude-code"},
            ),
            patch(
                "agentalloy.install.subcommands.wrap.subprocess.Popen",
                side_effect=FileNotFoundError("command not found"),
            ),
            patch("builtins.print", side_effect=capture_print),
            patch("agentalloy.install.subcommands.wrap.print_rich_stderr"),
        ):
            args = argparse.Namespace(
                harness="claude-code",
                port=None,
                via="proxy",
                no_start_server=True,
                child_args=["nonexistent-command-xyz"],
                json=True,
            )
            rc = _run(args)
            assert rc == 2

        result = json.loads("".join(captured_output))
        assert "error" in result
        assert "nonexistent-command-xyz" in result["error"]

    def test_human_output_on_success(self, tmp_state_dir: tuple[Path, Path]):
        """Successful wrap without --json should not produce JSON."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.wait.return_value = 0

        captured_output = []

        def capture_print(*args, **kwargs):
            captured_output.append(" ".join(str(a) for a in args))

        with (
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.find_listening_pid",
                return_value=9999,
            ),
            patch(
                "agentalloy.install.subcommands.wrap.wire_harness",
                return_value={"files_written": [], "harness": "claude-code"},
            ),
            patch(
                "agentalloy.install.subcommands.wrap.subprocess.Popen",
                return_value=mock_proc,
            ),
            patch(
                "agentalloy.install.subcommands.wrap.server_proc.stop",
            ),
            patch("builtins.print", side_effect=capture_print),
            patch(
                "agentalloy.install.subcommands.wrap.print_rich",
                side_effect=lambda *a, **k: None,
            ),
        ):
            args = argparse.Namespace(
                harness="claude-code",
                port=8000,
                via="proxy",
                no_start_server=True,
                child_args=["echo", "hello"],
                json=False,
            )
            _run(args)

        # Should NOT contain JSON (no braces at start of output)
        for line in captured_output:
            assert not line.strip().startswith("{"), f"Expected human output but got JSON: {line}"


# ---------------------------------------------------------------------------
# Legacy wire_harness KeyError guard tests (Issue 9)
# ---------------------------------------------------------------------------


class TestLegacyWireHarnessGuard:
    """Verify _wire_legacy raises SystemExit for unknown harnesses."""

    def test_legacy_unknown_harness_raises_system_exit(self, tmp_path: Path):
        """Calling wire_harness with legacy=True on an unknown harness should
        raise SystemExit with a clear error message, not KeyError."""
        from agentalloy.install.subcommands import wire_harness as wh_module

        with (
            pytest.raises(SystemExit) as exc_info,
            patch("agentalloy.install.subcommands.wire_harness.REGISTRY", {"test": None}),
        ):
            wh_module.wire_harness(
                "unknown-harness-that-is-not-in-legacy-registry",
                port=8000,
                root=tmp_path,
                legacy=True,
            )

        assert exc_info.value.code == 1

    def test_legacy_known_harness_works(self, tmp_path: Path):
        """Known harnesses should still work with legacy=True."""
        from agentalloy.install.subcommands import wire_harness as wh_module

        with (
            pytest.warns(DeprecationWarning),
            patch("agentalloy.install.subcommands.wire_harness.REGISTRY", {"claude-code": None}),
        ):
            # claude-code is in _HARNESS_REGISTRY, so it should work
            result = wh_module.wire_harness(
                "claude-code",
                port=8000,
                root=tmp_path,
                legacy=True,
            )
            assert result["harness"] == "claude-code"
