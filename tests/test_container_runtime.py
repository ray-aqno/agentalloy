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
