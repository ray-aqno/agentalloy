"""``container_runtime`` — runtime detection and build context location.

Provides utilities for container deployment: detecting podman/docker on PATH
and locating the agentalloy build context (for building the container image).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print(*args: Any, **kwargs: Any) -> None:
    """Print to stdout with optional rich markup (same as simple_setup)."""
    print(*args, **kwargs)


def _has_assets(d: Path) -> bool:
    """Return True if *d* looks like a valid agentalloy build context.

    Checks for the presence of both a compose file and a build file
    (Containerfile or Dockerfile).
    """
    default_compose = "compose.yaml"
    has_build_file = (d / "Containerfile").exists() or (d / "Dockerfile").exists()
    return (d / default_compose).exists() and has_build_file


# ---------------------------------------------------------------------------
# Runtime detection
# ---------------------------------------------------------------------------


def _detect_runtime_binary() -> str | None:
    """Find a container runtime binary on PATH.

    Search order: podman (preferred), docker (fallback).

    Returns
    -------
    str | None
        ``"podman"`` if podman is found (regardless of docker),
        ``"docker"`` if only docker is found,
        ``None`` if neither is on PATH.
    """
    for candidate in ("podman", "docker"):
        if shutil.which(candidate) is not None:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Build context location
# ---------------------------------------------------------------------------


def _locate_build_context() -> Path | None:
    """Locate the agentalloy build context for container image builds.

    Search order:

    1. **cwd** — if the user ran setup from inside the clone.
    2. **parents[4] of __file__** — editable install (points at repo root).
    3. **auto-clone** — clone into ``~/.cache/agentalloy/repo`` if git is
       available (for users who installed via ``uv tool install agentalloy``).

    Returns
    -------
    Path | None
        Path to ``compose.yaml`` in the found context, or ``None`` if all
        strategies fail.
    """
    default_compose = "compose.yaml"

    def _ensure_cached_repo() -> Path | None:
        """Clone (or refresh) the agentalloy repo into ~/.cache/agentalloy/repo.

        Returns the cache dir on success, None on failure. Uses --depth=1 so the
        clone is fast (~few MB). On refresh, hard-resets to origin/main so any
        local edits or stale state in the cache don't break the build context.
        """
        cache_dir = Path.home() / ".cache" / "agentalloy" / "repo"
        if shutil.which("git") is None:
            _print(
                "  [red]git not found on PATH — cannot clone the agentalloy repo "
                "for the build context.[/red]"
            )
            return None
        repo_url = "https://github.com/nrmeyers/agentalloy.git"
        # If the cache dir exists but isn't a valid git checkout (no .git/
        # — possibly a partial clone, leftover files, or a manually-placed
        # directory), `git clone <url> <dest>` would fail with "destination
        # path already exists and is not an empty directory". Nuke it so
        # the clone branch below can recreate cleanly.
        if cache_dir.exists() and not (cache_dir / ".git").exists():
            _print(
                f"  [yellow]-> Cache dir {cache_dir} exists but isn't a git "
                "checkout; recreating.[/yellow]"
            )
            try:
                shutil.rmtree(cache_dir)
            except OSError as exc:
                _print(f"  [red]Could not remove stale cache dir: {exc}[/red]")
                return None
        try:
            if (cache_dir / ".git").exists():
                _print(f"  [dim]-> Refreshing cached repo at {cache_dir}[/dim]")
                subprocess.run(
                    ["git", "-C", str(cache_dir), "fetch", "--depth=1", "origin", "main"],
                    check=True,
                    timeout=120,
                )
                subprocess.run(
                    ["git", "-C", str(cache_dir), "reset", "--hard", "origin/main"],
                    check=True,
                    timeout=60,
                )
            else:
                cache_dir.parent.mkdir(parents=True, exist_ok=True)
                _print(f"  [dim]-> Cloning {repo_url} into {cache_dir}[/dim]")
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth=1",
                        "--branch=main",
                        repo_url,
                        str(cache_dir),
                    ],
                    check=True,
                    timeout=180,
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            _print(f"  [red]git clone/fetch failed: {exc}[/red]")
            return None
        if not _has_assets(cache_dir):
            _print(
                f"  [red]Cached repo at {cache_dir} is missing {default_compose} "
                "or Containerfile after clone.[/red]"
            )
            return None
        return cache_dir

    # Strategy 1: cwd
    cwd = Path.cwd()
    if _has_assets(cwd):
        return cwd / default_compose

    # Strategy 2: parents[4] of __file__ (editable install)
    module_file = Path(__file__).resolve()
    editable_root = module_file.parents[4]
    if _has_assets(editable_root):
        return editable_root / default_compose

    # Strategy 3: auto-clone
    cached = _ensure_cached_repo()
    if cached is not None:
        return cached / default_compose

    return None
