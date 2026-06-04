# ruff: noqa: I001, PLC0415 -- testing private module members intentionally
"""Tests for the preflight container phase."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agentalloy.install.subcommands.preflight import (
    _check_compose_binary,  # pyright: ignore[reportPrivateUsage]
    _check_compose_file_present,  # pyright: ignore[reportPrivateUsage]
    _check_image_build_deps,  # pyright: ignore[reportPrivateUsage]
    _check_llama_server_present,  # pyright: ignore[reportPrivateUsage]
    _check_ollama_present,  # pyright: ignore[reportPrivateUsage]
    _detect_compose_binary,  # pyright: ignore[reportPrivateUsage]
    _try_brew_install,  # pyright: ignore[reportPrivateUsage]
    run_preflight,
)


class TestDetectComposeBinary:
    """Test _detect_compose_binary helper."""

    def test_podman_detected(self):
        """Podman is found and compose version succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("shutil.which", return_value="/usr/bin/podman"),
            patch("subprocess.run", return_value=mock_result),
        ):
            label, binary_path = _detect_compose_binary()
        assert label == "podman compose"
        assert binary_path == "/usr/bin/podman"

    def test_docker_fallback(self):
        """Podman missing, docker found."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        def which_side_effect(cmd: str) -> str | None:
            if cmd == "podman":
                return None
            return "/usr/bin/docker"

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", return_value=mock_result),
        ):
            label, binary_path = _detect_compose_binary()
        assert label == "docker compose"
        assert binary_path == "/usr/bin/docker"

    def test_none_found(self):
        """Neither podman nor docker found."""
        with patch("shutil.which", return_value=None):
            label, binary_path = _detect_compose_binary()
        assert label is None
        assert binary_path is None

    def test_podman_fails_docker_fallback(self):
        """Podman found but compose version fails, docker works."""

        def run_side_effect(cmd: Any, **kwargs: Any) -> Any:
            mock = MagicMock()
            # cmd is a list like ["/usr/bin/podman", "compose", "version"]
            cmd_str = " ".join(str(c) for c in cmd)
            if "podman" in cmd_str:
                mock.returncode = 1
            else:
                mock.returncode = 0
            return mock

        def which_side_effect(cmd: str) -> str | None:
            if cmd == "podman":
                return "/usr/bin/podman"
            return "/usr/bin/docker"

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            label, binary_path = _detect_compose_binary()
        assert label == "docker compose"
        assert binary_path == "/usr/bin/docker"


class TestComposeBinaryCheck:
    """Test _check_compose_binary check function."""

    def test_check_passes_when_podman_present(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch("shutil.which", return_value="/usr/bin/podman"),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = _check_compose_binary()
        assert result["passed"] is True
        assert "podman compose" in result["detail"]

    def test_check_fails_when_none_found(self):
        with patch("shutil.which", return_value=None):
            result = _check_compose_binary()
        assert result["passed"] is False
        assert result["severity"] == "fatal"
        assert "remediation" in result

    def test_check_returns_docker_when_fallback(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        def which_side_effect(cmd: str) -> str | None:
            return None if cmd == "podman" else "/usr/bin/docker"

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = _check_compose_binary()
        assert result["passed"] is True
        assert "docker compose" in result["detail"]

    def test_check_distinguishes_missing_compose_provider(self):
        """Podman on PATH but `podman compose version` exits non-zero
        (no compose provider plugin installed) — error must name the
        actual cause and remediation must point at a compose provider,
        not at re-installing podman."""
        failed = MagicMock()
        failed.returncode = 1
        failed.stderr = "Error: requires a compose provider, e.g. podman-compose"
        failed.stdout = ""

        def which_side_effect(cmd: str) -> str | None:
            return "/usr/bin/podman" if cmd == "podman" else None

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", return_value=failed),
        ):
            result = _check_compose_binary()

        assert result["passed"] is False
        assert "podman" in result["error"]
        assert "/usr/bin/podman" in result["error"]
        assert "no compose provider" in result["error"].lower()
        assert "podman-compose" in result["remediation"]


class TestComposeFilePresentCheck:
    """Test _check_compose_file_present check function."""

    def test_compose_file_present(self, tmp_path: Path):
        compose_file = tmp_path / "compose.yaml"
        compose_file.touch()
        result = _check_compose_file_present(str(compose_file))
        assert result["passed"] is True
        assert str(compose_file) in result["detail"]

    def test_compose_file_missing(self):
        result = _check_compose_file_present("/nonexistent/compose.yaml")
        assert result["passed"] is False
        assert "not found" in result["error"]

    def test_compose_file_none(self):
        result = _check_compose_file_present(None)
        assert result["passed"] is False
        assert "No compose file" in result["error"]


class TestImageBuildDepsCheck:
    """Test _check_image_build_deps check function."""

    def test_containerfile_present(self, tmp_path: Path):
        compose_file = tmp_path / "compose.yaml"
        compose_file.touch()
        containerfile = tmp_path / "Containerfile"
        containerfile.touch()
        result = _check_image_build_deps(str(compose_file))
        assert result["passed"] is True
        assert "Containerfile" in result["detail"]

    def test_dockerfile_fallback(self, tmp_path: Path):
        compose_file = tmp_path / "compose.yaml"
        compose_file.touch()
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.touch()
        result = _check_image_build_deps(str(compose_file))
        assert result["passed"] is True
        assert "Dockerfile" in result["detail"]

    def test_no_build_file(self, tmp_path: Path):
        compose_file = tmp_path / "compose.yaml"
        compose_file.touch()
        result = _check_image_build_deps(str(compose_file))
        assert result["passed"] is False
        assert "No Containerfile" in result["error"]

    def test_none_compose_file_skips(self):
        result = _check_image_build_deps(None)
        assert result["passed"] is True
        assert result["severity"] == "warn"


class TestContainerPhaseEnvelope:
    """Test the full container phase run_preflight."""

    def test_container_phase_runs_all_checks(self, tmp_path: Path):
        compose_file = tmp_path / "compose.yaml"
        compose_file.touch()
        containerfile = tmp_path / "Containerfile"
        containerfile.touch()

        mock_result = MagicMock()
        mock_result.returncode = 0

        def which_side_effect(cmd: str) -> str | None:
            return str(tmp_path / cmd) if cmd in ("podman",) else None

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = run_preflight(phase="container", compose_file=str(compose_file))

        check_names = [c["name"] for c in result["checks"]]
        assert "compose_binary" in check_names
        assert "compose_file_present" in check_names
        assert "port_free" in check_names
        assert "image_build_deps" in check_names

    def test_invalid_phase_raises(self):
        with pytest.raises(ValueError, match="invalid phase"):
            run_preflight(phase="invalid")


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
