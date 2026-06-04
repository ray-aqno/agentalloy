# ruff: noqa: I001, PLC0415 -- testing private module members intentionally
"""Tests for the preflight container phase."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agentalloy.install.subcommands.preflight import (
    _check_llama_server_present,  # pyright: ignore[reportPrivateUsage]
    _check_ollama_present,  # pyright: ignore[reportPrivateUsage]
    _try_brew_install,  # pyright: ignore[reportPrivateUsage]
    run_preflight,
)


class TestBrewAutoInstall:
    """Test macOS brew auto-install behavior in runner-phase checks.

    Brew auto-install is gated behind AGENTALLOY_PREFLIGHT_AUTO_INSTALL=1
    (opt-in). The autouse fixture below enables that opt-in for every test in
    this class; an explicit test verifies the gate is honored when the env
    var is unset.
    """

    @pytest.fixture(autouse=True)
    def _enable_auto_install_optin(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AGENTALLOY_PREFLIGHT_AUTO_INSTALL", "1")

    def test_try_brew_install_non_macos_noop(self):
        with patch("sys.platform", "linux"):
            ok, err = _try_brew_install("ollama-app", cask=True)
        assert ok is False
        assert err == "not macOS"

    def test_try_brew_install_no_brew_binary(self):
        with patch("sys.platform", "darwin"), patch("shutil.which", return_value=None):
            ok, err = _try_brew_install("llama.cpp")
        assert ok is False
        assert err == "brew not on PATH"

    def test_try_brew_install_disabled_without_optin(self, monkeypatch: pytest.MonkeyPatch):
        """Without AGENTALLOY_PREFLIGHT_AUTO_INSTALL=1, brew install is a no-op."""
        monkeypatch.delenv("AGENTALLOY_PREFLIGHT_AUTO_INSTALL", raising=False)
        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/opt/homebrew/bin/brew"),
        ):
            ok, err = _try_brew_install("ollama-app", cask=True)
        assert ok is False
        assert "auto-install disabled" in err

    def test_try_brew_install_redirects_stdout_to_stderr(self):
        """brew stdout must not corrupt --json output."""
        import sys as _sys

        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            captured["stdout"] = kwargs.get("stdout")
            captured["cmd"] = cmd
            return MagicMock(returncode=0)

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/opt/homebrew/bin/brew"),
            patch("subprocess.run", side_effect=fake_run),
        ):
            ok, err = _try_brew_install("ollama-app", cask=True)
        assert ok is True
        assert err is None
        assert captured["stdout"] is _sys.stderr
        assert captured["cmd"] == ["brew", "install", "--cask", "ollama-app"]

    def test_ollama_present_skips_brew_when_already_installed(self):
        with patch("shutil.which", return_value="/usr/local/bin/ollama"):
            result = _check_ollama_present()
        assert result["passed"] is True
        assert "ollama at /usr/local/bin/ollama" in result["detail"]

    def test_ollama_present_brew_installs_then_resolves(self):
        # Sequence: ollama(missing) → brew(present, gate) → brew(present, in
        # _try_brew_install) → ollama(present after install).
        which_results = {
            "ollama": iter([None, "/opt/homebrew/bin/ollama"]),
            "brew": iter(["/opt/homebrew/bin/brew", "/opt/homebrew/bin/brew"]),
        }

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", side_effect=lambda cmd: next(which_results[cmd])),
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
        ):
            result = _check_ollama_present()
        assert result["passed"] is True
        assert "installed via brew" in result["detail"]

    def test_ollama_present_brew_succeeds_but_binary_still_missing(self):
        """Distinguish 'install failed' from 'install succeeded, PATH stale'."""
        which_results = {
            "ollama": iter([None, None]),
            "brew": iter(["/opt/homebrew/bin/brew", "/opt/homebrew/bin/brew"]),
        }

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", side_effect=lambda cmd: next(which_results[cmd])),
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
        ):
            result = _check_ollama_present()
        assert result["passed"] is False
        assert "succeeded but `ollama` is still not on PATH" in result["error"]

    def test_ollama_present_non_macos_prints_instructions(self):
        with patch("sys.platform", "linux"), patch("shutil.which", return_value=None):
            result = _check_ollama_present()
        assert result["passed"] is False
        assert "ollama not found on PATH" in result["error"]
        assert "brew install --cask ollama-app" in result["remediation"]

    def test_llama_server_brew_installs_then_resolves(self):
        which_results = {
            "llama-server": iter([None, "/opt/homebrew/bin/llama-server"]),
            "brew": iter(["/opt/homebrew/bin/brew", "/opt/homebrew/bin/brew"]),
        }

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", side_effect=lambda cmd: next(which_results[cmd])),
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
        ):
            result = _check_llama_server_present()
        assert result["passed"] is True
        assert "installed via brew" in result["detail"]

    def test_llama_server_brew_succeeds_but_binary_still_missing(self):
        which_results = {
            "llama-server": iter([None, None]),
            "brew": iter(["/opt/homebrew/bin/brew", "/opt/homebrew/bin/brew"]),
        }

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", side_effect=lambda cmd: next(which_results[cmd])),
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
        ):
            result = _check_llama_server_present()
        assert result["passed"] is False
        assert "succeeded but `llama-server` is still not on PATH" in result["error"]


# ---------------------------------------------------------------------------
# New container-phase checks (preflight refactor)
# ---------------------------------------------------------------------------


class TestCheckRuntimeBinary:
    """UT-11, UT-12, UT-13: _check_runtime_binary() — podman preferred, docker fallback."""

    def test_podman_on_path_passes(self):
        """UT-11: _check_runtime_binary() passes when podman on PATH."""
        from agentalloy.install.subcommands.preflight import _check_runtime_binary

        result = _check_runtime_binary("podman")
        assert result["passed"] is True
        assert "podman" in result["detail"]

    def test_only_docker_on_path_passes(self):
        """UT-12: _check_runtime_binary() passes when only docker on PATH."""
        from agentalloy.install.subcommands.preflight import _check_runtime_binary

        result = _check_runtime_binary("docker")
        assert result["passed"] is True
        assert "docker" in result["detail"]

    def test_neither_binary_fails(self):
        """UT-13: _check_runtime_binary() fails when neither podman nor docker on PATH."""
        from agentalloy.install.subcommands.preflight import _check_runtime_binary

        result = _check_runtime_binary(None)
        assert result["passed"] is False
        assert result["severity"] == "fatal"
        assert "remediation" in result
        assert "podman" in result["error"] or "docker" in result["error"]


class TestCheckBuildContext:
    """UT-14, UT-15, UT-16: _check_build_context() — verifies build assets."""

    def test_all_assets_present_passes(self, tmp_path: Path):
        """UT-14: _check_build_context() passes when all assets present."""
        from agentalloy.install.subcommands.preflight import _check_build_context

        (tmp_path / "Containerfile").touch()
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "uv.lock").touch()
        result = _check_build_context(str(tmp_path))
        assert result["passed"] is True
        assert "Containerfile" in result["detail"]

    def test_containerfile_missing_fails(self, tmp_path: Path):
        """UT-15: _check_build_context() fails when Containerfile missing."""
        from agentalloy.install.subcommands.preflight import _check_build_context

        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "uv.lock").touch()
        result = _check_build_context(str(tmp_path))
        assert result["passed"] is False
        assert "Containerfile" in result["error"]

    def test_pyproject_missing_fails(self, tmp_path: Path):
        """UT-16: _check_build_context() fails when pyproject.toml missing."""
        from agentalloy.install.subcommands.preflight import _check_build_context

        (tmp_path / "Containerfile").touch()
        (tmp_path / "uv.lock").touch()
        result = _check_build_context(str(tmp_path))
        assert result["passed"] is False
        assert "pyproject.toml" in result["error"]

    def test_uv_lock_missing_fails(self, tmp_path: Path):
        """_check_build_context() fails when uv.lock missing."""
        from agentalloy.install.subcommands.preflight import _check_build_context

        (tmp_path / "Containerfile").touch()
        (tmp_path / "pyproject.toml").touch()
        result = _check_build_context("")
        assert result["passed"] is False

    def test_empty_path_fails(self):
        """_check_build_context() fails when path is empty string."""
        from agentalloy.install.subcommands.preflight import _check_build_context

        result = _check_build_context("")
        assert result["passed"] is False


class TestCheckNameConflicts:
    """UT-17, UT-18: _check_name_conflicts() — existing container detection."""

    def test_detects_existing_container(self):
        """UT-17: _check_name_conflicts() detects existing agentalloy container."""
        from agentalloy.install.subcommands.preflight import _check_name_conflicts

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123def456"

        def run_side_effect(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = "abc123def456"
            return mock

        with patch("subprocess.run", side_effect=run_side_effect):
            result = _check_name_conflicts("podman")
        assert result["passed"] is False
        assert "agentalloy" in result["error"].lower() or "already" in result["error"].lower()

    def test_no_conflict_passes(self):
        """UT-18: _check_name_conflicts() passes when no conflict."""
        from agentalloy.install.subcommands.preflight import _check_name_conflicts

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "container not found"

        def run_side_effect(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 1
            mock.stdout = ""
            mock.stderr = "Error: no such container"
            return mock

        with patch("subprocess.run", side_effect=run_side_effect):
            result = _check_name_conflicts("podman")
        assert result["passed"] is True


class TestCheckVolumeExists:
    """_check_volume_exists() — existing volume detection."""

    def test_detects_existing_volume(self):
        """Volume already exists — should pass (volume creation is idempotent)."""
        from agentalloy.install.subcommands.preflight import _check_volume_exists

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "agentalloy-data"

        def run_side_effect(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = "agentalloy-data"
            return mock

        with patch("subprocess.run", side_effect=run_side_effect):
            result = _check_volume_exists("podman")
        assert result["passed"] is True

    def test_no_volume_passes(self):
        """Volume does not exist — OK for preflight (creation happens later)."""
        from agentalloy.install.subcommands.preflight import _check_volume_exists

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "no such volume"

        def run_side_effect(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 1
            mock.stderr = "Error: no such volume: agentalloy-data"
            return mock

        with patch("subprocess.run", side_effect=run_side_effect):
            result = _check_volume_exists("podman")
        assert result["passed"] is True


class TestImageBuildDepsContainerfileOnly:
    """_check_image_build_deps() — no Dockerfile fallback after refactor."""

    def test_containerfile_only_passes(self, tmp_path: Path):
        """Containerfile present — passes."""
        from agentalloy.install.subcommands.preflight import _check_image_build_deps

        (tmp_path / "Containerfile").touch()
        result = _check_image_build_deps(str(tmp_path))
        assert result["passed"] is True
        assert "Containerfile" in result["detail"]

    def test_dockerfile_only_fails(self, tmp_path: Path):
        """Dockerfile only — should fail (no fallback after refactor)."""
        from agentalloy.install.subcommands.preflight import _check_image_build_deps

        (tmp_path / "Dockerfile").touch()
        result = _check_image_build_deps(str(tmp_path))
        assert result["passed"] is False
        assert "Containerfile" in result["error"]

    def test_none_path_skips(self):
        """None/empty path — passes with warning."""
        from agentalloy.install.subcommands.preflight import _check_image_build_deps

        result = _check_image_build_deps(None)
        assert result["passed"] is True
        assert result["severity"] == "warn"


class TestContainerPhaseEnvelope:
    """IT-10, IT-11: Full container phase integration tests."""

    def test_container_phase_all_pass(self, tmp_path: Path):
        """IT-10: Preflight container phase — all checks pass."""
        from agentalloy.install.subcommands.preflight import run_preflight

        # Create build context assets
        (tmp_path / "Containerfile").touch()
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "uv.lock").touch()

        mock_no_container = MagicMock()
        mock_no_container.returncode = 1
        mock_no_container.stdout = ""
        mock_no_container.stderr = "no such container"

        mock_ok = MagicMock()
        mock_ok.returncode = 0
        mock_ok.stdout = ""

        def run_side_effect(cmd, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "ps" in cmd_str and "--filter" in cmd_str:
                return mock_no_container
            if "volume" in cmd_str and "inspect" in cmd_str:
                return mock_ok
            return mock_ok

        def which_side_effect(cmd: str) -> str | None:
            return str(tmp_path / cmd) if cmd == "podman" else None

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = run_preflight(
                phase="container",
                build_context=str(tmp_path),
                runtime="podman",
            )

        check_names = [c["name"] for c in result["checks"]]
        assert "runtime_binary" in check_names
        assert "build_context" in check_names
        assert "name_conflicts" in check_names
        assert "volume_exists" in check_names
        assert "port_free" in check_names
        assert "image_build_deps" in check_names

        # No fatal failures
        assert result["fatal_failures"] == []

    def test_container_phase_mixed_failures(self, tmp_path: Path):
        """IT-11: Preflight container phase — mixed failures."""
        from agentalloy.install.subcommands.preflight import run_preflight

        # Create build context assets
        (tmp_path / "Containerfile").touch()
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "uv.lock").touch()

        mock_existing_container = MagicMock()
        mock_existing_container.returncode = 0
        mock_existing_container.stdout = "abc123"

        def run_side_effect(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = "abc123"
            mock.stderr = ""
            cmd_str = " ".join(str(c) for c in cmd)
            if "ps" in cmd_str and "--filter" in cmd_str:
                return mock_existing_container
            return mock
        mock_ok = MagicMock(returncode=0)

        def which_side_effect(cmd: str) -> str | None:
            return str(tmp_path / cmd) if cmd == "podman" else None

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = run_preflight(
                phase="container",
                build_context=str(tmp_path),
                runtime="podman",
            )

        # name_conflicts should be a failure
        check_map = {c["name"]: c for c in result["checks"]}
        assert check_map["name_conflicts"]["passed"] is False
        assert "name_conflicts" in result["fatal_failures"]

