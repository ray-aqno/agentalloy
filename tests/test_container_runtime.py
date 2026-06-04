"""Tests for container_runtime module — runtime detection and build context."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# UT-1: _detect_runtime_binary
# ---------------------------------------------------------------------------


class TestDetectRuntimeBinary:
    """Test _detect_runtime_binary() priority: podman > docker > None."""

    def test_both_podman_and_docker_returns_podman(self, tmp_path: Path):
        """When both podman and docker are on PATH, prefer podman."""
        # Create fake binaries
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "podman").write_text("#!/bin/sh\n")
        (bin_dir / "docker").write_text("#!/bin/sh\n")
        (bin_dir / "podman").chmod(0o755)
        (bin_dir / "docker").chmod(0o755)

        with patch.dict(os.environ, {"PATH": str(bin_dir)}, clear=True):
            from agentalloy.install.subcommands.container_runtime import (
                _detect_runtime_binary,
            )

            result = _detect_runtime_binary()
            assert result == "podman"

    def test_only_docker_returns_docker(self, tmp_path: Path):
        """When only docker is on PATH, return docker."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "docker").write_text("#!/bin/sh\n")
        (bin_dir / "docker").chmod(0o755)

        with patch.dict(os.environ, {"PATH": str(bin_dir)}, clear=True):
            from agentalloy.install.subcommands.container_runtime import (
                _detect_runtime_binary,
            )

            result = _detect_runtime_binary()
            assert result == "docker"

    def test_only_podman_returns_podman(self, tmp_path: Path):
        """When only podman is on PATH, return podman."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "podman").write_text("#!/bin/sh\n")
        (bin_dir / "podman").chmod(0o755)

        with patch.dict(os.environ, {"PATH": str(bin_dir)}, clear=True):
            from agentalloy.install.subcommands.container_runtime import (
                _detect_runtime_binary,
            )

            result = _detect_runtime_binary()
            assert result == "podman"

    def test_neither_returns_none(self, tmp_path: Path):
        """When neither podman nor docker is on PATH, return None."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()

        with patch.dict(os.environ, {"PATH": str(bin_dir)}, clear=True):
            from agentalloy.install.subcommands.container_runtime import (
                _detect_runtime_binary,
            )

            result = _detect_runtime_binary()
            assert result is None


# ---------------------------------------------------------------------------
# UT-2: _locate_build_context
# ---------------------------------------------------------------------------


class TestLocateBuildContext:
    """Test _locate_build_context() search order: cwd -> parents[4] -> auto-clone -> None."""

    def _make_minimal_context(self, d: Path) -> Path:
        """Create minimal build context assets in directory d, return compose path."""
        (d / "compose.yaml").write_text("services: {}\n")
        (d / "Containerfile").write_text("FROM python:3.11\n")
        return d / "compose.yaml"

    def test_finds_in_cwd_first(self, tmp_path: Path):
        """When cwd has build context assets, return cwd compose path."""
        # Create minimal context in a subdirectory and make it cwd
        ctx_dir = tmp_path / "my-clone"
        ctx_dir.mkdir()
        self._make_minimal_context(ctx_dir)

        with patch("agentalloy.install.subcommands.container_runtime.Path.cwd", return_value=ctx_dir):
            from agentalloy.install.subcommands.container_runtime import (
                _locate_build_context,
            )

            result = _locate_build_context()
            assert result == ctx_dir / "compose.yaml"

    def test_falls_back_to_parents4(self, tmp_path: Path):
        """When cwd lacks assets, fall back to parents[4] of __file__."""
        import agentalloy.install.subcommands.container_runtime as mod
        from agentalloy.install.subcommands.container_runtime import (
            _locate_build_context,
        )

        # Create context at parents[4] of the module file.
        # Real path: src/agentalloy/install/subcommands/container_runtime.py
        # parents[4] = repo root.  Replicate this depth.
        ctx_dir = tmp_path / "agentalloy"
        ctx_dir.mkdir()
        self._make_minimal_context(ctx_dir)

        # Fake module path mirrors real structure:
        #   ctx_dir/src/agentalloy/install/subcommands/container_runtime.py
        fake_module_file = str(
            ctx_dir / "src" / "agentalloy" / "install" / "subcommands"
            / "container_runtime.py"
        )
        Path(fake_module_file).parents[0].mkdir(parents=True, exist_ok=True)

        # Patch Path.cwd to return a non-matching directory
        fake_cwd = tmp_path / "somewhere"
        fake_cwd.mkdir()

        # Patch the module's __file__ to point at our temp location
        original_file = mod.__file__
        mod.__file__ = fake_module_file

        try:
            with patch("agentalloy.install.subcommands.container_runtime.Path.cwd", return_value=fake_cwd):
                result = _locate_build_context()
                assert result == ctx_dir / "compose.yaml"
        finally:
            mod.__file__ = original_file

    def test_falls_back_to_auto_clone_when_both_fail(self, tmp_path: Path):
        """When cwd and parents[4] lack assets, try auto-clone."""
        import agentalloy.install.subcommands.container_runtime as mod
        from agentalloy.install.subcommands.container_runtime import (
            _locate_build_context,
        )

        fake_cwd = tmp_path / "no-context"
        fake_cwd.mkdir()

        # parents[4] of module won't have assets
        repo_root = tmp_path / "agentalloy"
        repo_root.mkdir()
        (repo_root / "src").mkdir()
        (repo_root / "src" / "agentalloy").mkdir()
        (repo_root / "src" / "agentalloy" / "install").mkdir()
        (repo_root / "src" / "agentalloy" / "install" / "subcommands").mkdir(parents=True)
        # Deliberately NOT creating compose.yaml or Containerfile here

        original_file = mod.__file__
        fake_module_file = str(
            repo_root / "src" / "agentalloy" / "install" / "subcommands"
            / "container_runtime.py"
        )
        mod.__file__ = fake_module_file

        # Use a fake home so the cache dir is inside tmp_path
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        cache_dir = fake_home / ".cache" / "agentalloy" / "repo"
        cache_dir.mkdir(parents=True)
        self._make_minimal_context(cache_dir)

        try:
            # _has_assets returns True only for the cache dir (auto-clone path)
            def _has_assets_side_effect(d: Path) -> bool:
                return d == cache_dir

            with patch("agentalloy.install.subcommands.container_runtime.Path.cwd", return_value=fake_cwd):
                with patch("agentalloy.install.subcommands.container_runtime.Path.home", return_value=fake_home):
                    with patch("agentalloy.install.subcommands.container_runtime.shutil.which", return_value="/usr/bin/git"):
                        with patch("agentalloy.install.subcommands.container_runtime.subprocess.run") as mock_run:
                            mock_run.return_value = subprocess.CompletedProcess(
                                args=["git", "clone"], returncode=0
                            )
                            with patch(
                                "agentalloy.install.subcommands.container_runtime._has_assets",
                                side_effect=_has_assets_side_effect,
                            ):
                                result = _locate_build_context()
                                assert result == cache_dir / "compose.yaml"
                                # Verify clone was attempted
                                mock_run.assert_called()
        finally:
            mod.__file__ = original_file

    def test_returns_none_when_all_fails(self, tmp_path: Path):
        """When all strategies fail, return None."""
        import agentalloy.install.subcommands.container_runtime as mod
        from agentalloy.install.subcommands.container_runtime import (
            _locate_build_context,
        )

        fake_cwd = tmp_path / "no-context"
        fake_cwd.mkdir()

        repo_root = tmp_path / "agentalloy"
        repo_root.mkdir()
        (repo_root / "install").mkdir()
        (repo_root / "install" / "subcommands").mkdir(parents=True)
        # No compose.yaml or Containerfile

        original_file = mod.__file__
        fake_module_file = str(repo_root / "install" / "subcommands" / "container_runtime.py")
        mod.__file__ = fake_module_file

        try:
            with patch("agentalloy.install.subcommands.container_runtime.Path.cwd", return_value=fake_cwd):
                with patch("agentalloy.install.subcommands.container_runtime.shutil.which", return_value=None):
                    result = _locate_build_context()
                    assert result is None
        finally:
            mod.__file__ = original_file


# ---------------------------------------------------------------------------
# UT-3: _build_image
# ---------------------------------------------------------------------------


class TestBuildImage:
    """Test _build_image() constructs correct container build command."""

    def test_build_image_runs_podman_build_with_correct_flags(self, tmp_path: Path):
        """_build_image() runs runtime build -t agentalloy:local -f Containerfile <context>."""
        with patch("agentalloy.install.subcommands.container_runtime.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["podman", "build", "-t", "agentalloy:local", "-f", "Containerfile", str(tmp_path)],
                returncode=0,
            )
            from agentalloy.install.subcommands.container_runtime import _build_image

            result = _build_image("podman", tmp_path)

            assert result == 0

    def test_build_image_uses_correct_image_tag_and_dockerfile(self, tmp_path: Path):
        """_build_image() passes -t agentalloy:local -f Containerfile to the runtime."""
        # Create a minimal Containerfile so the command doesn't fail on missing file
        (tmp_path / "Containerfile").write_text("FROM python:3.11\n")

        with patch("agentalloy.install.subcommands.container_runtime.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["podman", "build", "-t", "agentalloy:local", "-f", "Containerfile", str(tmp_path)],
                returncode=0,
            )
            from agentalloy.install.subcommands.container_runtime import _build_image

            _build_image("podman", tmp_path)

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "podman" in cmd[0]
            assert "build" in cmd
            assert "-t" in cmd
            assert "agentalloy:local" in cmd
            assert "-f" in cmd
            assert "Containerfile" in cmd
            assert str(tmp_path) in cmd

    def test_build_image_returns_nonzero_on_failure(self, tmp_path: Path):
        """_build_image() returns the non-zero exit code when build fails."""
        with patch("agentalloy.install.subcommands.container_runtime.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=127, cmd="podman build", stderr="command not found"
            )
            from agentalloy.install.subcommands.container_runtime import _build_image

            result = _build_image("podman", tmp_path)

            assert result == 127

    def test_build_image_has_600s_timeout(self, tmp_path: Path):
        """_build_image() passes timeout=600 to subprocess.run."""
        with patch("agentalloy.install.subcommands.container_runtime.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["podman", "build"], returncode=0
            )
            from agentalloy.install.subcommands.container_runtime import _build_image

            _build_image("podman", tmp_path)

            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("timeout") == 600


# ---------------------------------------------------------------------------
# UT-4: _ensure_volume
# ---------------------------------------------------------------------------


class TestEnsureVolume:
    """Test _ensure_volume() handles volume creation and idempotency."""

    def test_ensure_volume_runs_volume_create(self):
        """_ensure_volume() runs runtime volume create agentalloy-data."""
        with patch("agentalloy.install.subcommands.container_runtime.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["podman", "volume", "create", "agentalloy-data"],
                returncode=0,
            )
            from agentalloy.install.subcommands.container_runtime import _ensure_volume

            _ensure_volume("podman")

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "volume" in cmd
            assert "create" in cmd
            assert "agentalloy-data" in cmd

    def test_ensure_volume_handles_already_exists(self):
        """_ensure_volume() does not raise when runtime reports volume already exists."""
        with patch("agentalloy.install.subcommands.container_runtime.subprocess.run") as mock_run:
            # Some runtimes return non-zero or stderr for "already exists"
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["podman", "volume", "create", "agentalloy-data"],
                stderr="podman: volume agentalloy-data already exists\n",
            )
            from agentalloy.install.subcommands.container_runtime import _ensure_volume

            # Should not raise
            _ensure_volume("podman")

    def test_ensure_volume_raises_on_unexpected_error(self):
        """_ensure_volume() raises on errors other than 'already exists'."""
        with patch("agentalloy.install.subcommands.container_runtime.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["podman", "volume", "create", "agentalloy-data"],
                stderr="permission denied\n",
            )
            from agentalloy.install.subcommands.container_runtime import _ensure_volume

            with pytest.raises(subprocess.CalledProcessError):
                _ensure_volume("podman")


# ---------------------------------------------------------------------------
# UT-5: _ensure_ollama_dir
# ---------------------------------------------------------------------------


class TestEnsureOllamaDir:
    """Test _ensure_ollama_dir() creates ~/.ollama if missing."""

    def test_ensure_ollama_dir_creates_directory(self, tmp_path: Path):
        """_ensure_ollama_dir() creates ~/.ollama when it doesn't exist."""
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        ollama_dir = fake_home / ".ollama"
        assert not ollama_dir.exists()

        with patch("agentalloy.install.subcommands.container_runtime.Path.home", return_value=fake_home):
            from agentalloy.install.subcommands.container_runtime import _ensure_ollama_dir

            _ensure_ollama_dir()

            assert ollama_dir.exists()
            assert ollama_dir.is_dir()

    def test_ensure_ollama_dir_is_idempotent(self, tmp_path: Path):
        """_ensure_ollama_dir() does not fail when ~/.ollama already exists."""
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        ollama_dir = fake_home / ".ollama"
        ollama_dir.mkdir()

        with patch("agentalloy.install.subcommands.container_runtime.Path.home", return_value=fake_home):
            from agentalloy.install.subcommands.container_runtime import _ensure_ollama_dir

            # Should not raise
            _ensure_ollama_dir()

            assert ollama_dir.exists()


# ---------------------------------------------------------------------------
# UT-6: _generate_entrypoint — writes valid bash script with all bootstrap steps
# ---------------------------------------------------------------------------


class TestGenerateEntrypoint:
    """Test _generate_entrypoint() writes a valid bash script to a temp file."""

    def test_generate_entrypoint_returns_path(self, tmp_path: Path):
        """_generate_entrypoint() returns a Path that exists."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        result = _generate_entrypoint("")

        assert isinstance(result, Path)
        assert result.exists()

    def test_generate_entrypoint_writes_bash_script(self, tmp_path: Path):
        """_generate_entrypoint() writes a valid bash script with #!/bin/bash."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        result = _generate_entrypoint("")
        content = result.read_text()

        assert content.startswith("#!/bin/bash")

    def test_generate_entrypoint_contains_ollama_install(self, tmp_path: Path):
        """Generated entrypoint contains Ollama install step."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        content = _generate_entrypoint("").read_text()

        assert "ollama" in content.lower()

    def test_generate_entrypoint_contains_ollama_start(self, tmp_path: Path):
        """Generated entrypoint contains ollama serve start."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        content = _generate_entrypoint("").read_text()

        assert "ollama serve" in content

    def test_generate_entrypoint_contains_model_pull(self, tmp_path: Path):
        """Generated entrypoint contains embedding model pull step."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        content = _generate_entrypoint("").read_text()

        assert "qwen3-embedding" in content

    def test_generate_entrypoint_contains_migrations(self, tmp_path: Path):
        """Generated entrypoint contains migrations step."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        content = _generate_entrypoint("").read_text()

        assert "agentalloy.migrate" in content

    def test_generate_entrypoint_contains_uvicorn_start(self, tmp_path: Path):
        """Generated entrypoint contains uvicorn start step."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        content = _generate_entrypoint("").read_text()

        assert "uvicorn" in content

    def test_generate_entrypoint_contains_sigterm_trap(self, tmp_path: Path):
        """Generated entrypoint contains SIGTERM trap for graceful shutdown."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        content = _generate_entrypoint("").read_text()

        assert "SIGTERM" in content

    def test_generate_entrypoint_is_executable(self, tmp_path: Path):
        """Generated entrypoint has executable permissions (0600)."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        result = _generate_entrypoint("")
        mode = result.stat().st_mode & 0o777

        assert mode == 0o600

    def test_generate_entrypoint_uses_temp_dir(self, tmp_path: Path):
        """Generated entrypoint is placed in a temp directory."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        result = _generate_entrypoint("")

        # The file should be in a temp directory (e.g., /tmp or similar)
        assert result.is_file()


# ---------------------------------------------------------------------------
# UT-7: _generate_entrypoint — no install-packs when packs is empty
# ---------------------------------------------------------------------------


class TestGenerateEntrypointNoPacks:
    """Test _generate_entrypoint() when packs is empty."""

    def test_no_install_packs_when_packs_empty(self, tmp_path: Path):
        """When packs='', the generated script should not contain install-packs."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        content = _generate_entrypoint("").read_text()

        assert "install-packs" not in content


# ---------------------------------------------------------------------------
# UT-8: _generate_entrypoint — install-packs present when packs non-empty
# ---------------------------------------------------------------------------


class TestGenerateEntrypointWithPacks:
    """Test _generate_entrypoint() when packs is non-empty."""

    def test_install_packs_present_when_packs_set(self, tmp_path: Path):
        """When packs='foundation,tooling', the generated script should contain install-packs."""
        from agentalloy.install.subcommands.container_runtime import _generate_entrypoint

        content = _generate_entrypoint("foundation,tooling").read_text()

        assert "install-packs" in content
        assert "foundation,tooling" in content


# ---------------------------------------------------------------------------
# UT-9: _cleanup_temp_entrypoint — removes the temp file
# ---------------------------------------------------------------------------


class TestCleanupTempEntrypoint:
    """Test _cleanup_temp_entrypoint() removes the temp file."""

    def test_cleanup_removes_file(self, tmp_path: Path):
        """_cleanup_temp_entrypoint() removes the temp file."""
        from agentalloy.install.subcommands.container_runtime import (
            _cleanup_temp_entrypoint,
            _generate_entrypoint,
        )

        entrypoint = _generate_entrypoint("")
        assert entrypoint.exists()

        _cleanup_temp_entrypoint(entrypoint)

        assert not entrypoint.exists()

    def test_cleanup_is_idempotent(self, tmp_path: Path):
        """_cleanup_temp_entrypoint() does not raise if file is already gone."""
        from agentalloy.install.subcommands.container_runtime import (
            _cleanup_temp_entrypoint,
        )

        # Should not raise even if the file doesn't exist
        _cleanup_temp_entrypoint(tmp_path / "nonexistent.sh")
