"""``container_runtime`` — runtime detection and build context location.

Provides utilities for container deployment: detecting podman/docker on PATH
and locating the agentalloy build context (for building the container image).
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
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


# ---------------------------------------------------------------------------
# Image build
# ---------------------------------------------------------------------------


def _build_image(runtime: str, context: Path) -> int:
    """Build the agentalloy container image.

    Runs ``{runtime} build -t agentalloy:local -f Containerfile <context>``
    with a 600-second timeout.  Build output is captured and written to a
    log file on failure for debugging.  Returns the exit code (0 on success).

    Parameters
    ----------
    runtime : str
        Container runtime binary (e.g. ``"podman"`` or ``"docker"``).
    context : Path
        Path to the build context directory.

    Returns
    -------
    int
        Exit code from the runtime command.
    """
    log_path = Path(tempfile.gettempdir()) / "agentalloy-build.log"
    try:
        subprocess.run(
            [
                runtime,
                "build",
                "-t",
                "agentalloy:local",
                "-f",
                "Containerfile",
                str(context),
            ],
            check=True,
            timeout=600,
            capture_output=True,
        )
        return 0
    except subprocess.CalledProcessError as exc:
        # Write captured build output to log file for debugging
        log_path.write_text(
            f"=== agentalloy build failed (exit {exc.returncode}) ===\n"
            f"Command: {shlex.join(exc.cmd)}\n\n"
            f"--- stdout ---\n{(exc.output or b'').decode(errors='replace')}\n"
            f"--- stderr ---\n{(exc.stderr or b'').decode(errors='replace')}\n"
        )
        _print(f"  [red]Build failed (exit {exc.returncode}) — log: {log_path}[/red]")
        return exc.returncode
    except subprocess.TimeoutExpired:
        _print("  [red]Build timed out after 600s[/red]")
        return 1


# ---------------------------------------------------------------------------
# Volume management
# ---------------------------------------------------------------------------


def _ensure_volume(runtime: str) -> None:
    """Create the agentalloy data volume if it doesn't already exist.

    Idempotent — silently ignores the "volume already exists" error.

    Parameters
    ----------
    runtime : str
        Container runtime binary (e.g. ``"podman"`` or ``"docker"``).

    Raises
    ------
    subprocess.CalledProcessError
        If the volume creation fails for a reason other than "already exists".
    """
    try:
        subprocess.run(
            [runtime, "volume", "create", "agentalloy-data"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode(errors="replace").lower()
        if "already exists" in stderr:
            return
        raise


# ---------------------------------------------------------------------------
# Ollama directory
# ---------------------------------------------------------------------------


def _ensure_ollama_dir() -> None:
    """Ensure ``~/.ollama`` exists.

    Creates the directory (with ``parents=True``) if it doesn't already
    exist.  Idempotent — no-op if the directory already exists.
    """
    Path.home().joinpath(".ollama").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Entrypoint generation
# ---------------------------------------------------------------------------


def _generate_entrypoint(packs: str) -> Path:
    """Generate an entrypoint wrapper script and return its temp file path.

    The entrypoint is a bash script that handles in-container bootstrap:

    1. Check if ``$APP_DIR/.bootstrap-complete`` exists — if so, skip to uvicorn.
    2. Check if Ollama is installed; download and install if needed.
    3. Start ``ollama serve`` in the background on ``127.0.0.1:11434``.
    4. Poll ``http://127.0.0.1:11434`` until Ollama is ready (30 s timeout).
    5. Check if the embedding model (``qwen3-embedding:0.6b``) is cached;
       pull it if not.
    6. Run migrations (``uv run agentalloy migrate``).
    7. If *packs* is non-empty, run ``uv run agentalloy install-packs --packs <packs>``.
    8. Create the ``$APP_DIR/.bootstrap-complete`` flag file.
    9. Trap SIGTERM for graceful shutdown (only if Ollama was started).
    10. Start uvicorn on ``0.0.0.0:47950``.

    Parameters
    ----------
    packs : str
        Comma-separated list of packs to install, or empty string.

    Returns
    -------
    Path
        Path to the generated entrypoint script (in the system temp directory).
    """
    script = _build_entrypoint_script(packs)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sh")  # noqa: SIM115 (file must persist for container mount)
    tmp.write(script.encode())
    tmp.close()
    entrypoint = Path(tmp.name)
    entrypoint.chmod(0o700)
    return entrypoint


def _build_entrypoint_script(packs: str) -> str:
    """Build the entrypoint wrapper script as a string."""
    lines = [
        "#!/bin/bash",
        "set -e",
        "",
        "# App directory (configurable via APP_DIR env var, default /app)",
        "APP_DIR=${APP_DIR:-/app}",
        "",
        "# Bootstrap completion check (early exit if already complete)",
        'if [ -f "$APP_DIR/.bootstrap-complete" ]; then',
        '    echo ">> Bootstrap already complete - skipping to uvicorn"',
        "else",
        "    # Ollama installation",
        "    if ! command -v ollama &> /dev/null; then",
        '        echo ">> Installing Ollama..."',
        "        curl -fsSL https://ollama.ai/install.sh | sh",
        "    fi",
        "",
        "    # Start Ollama",
        '    echo ">> Starting Ollama..."',
        "    ollama serve --host 127.0.0.1:11434 &",
        "    OLLAMA_PID=$!",
        "",
        "    # Wait for Ollama to be ready (30 s timeout)",
        "    for i in $(seq 1 30); do",
        "        if curl -sf http://127.0.0.1:11434 > /dev/null 2>&1; then",
        '            echo ">> Ollama is ready"',
        "            break",
        "        fi",
        "        sleep 1",
        "    done",
        "",
        "    # Pull embedding model",
        '    echo ">> Checking embedding model..."',
        "    if ! ollama list | grep -q qwen3-embedding; then",
        '        echo ">> Pulling qwen3-embedding:0.6b..."',
        "        ollama pull qwen3-embedding:0.6b",
        "    fi",
        "",
        "    # Run migrations",
        '    echo ">> Running migrations..."',
        "    uv run agentalloy migrate",
        "",
        "    # Pack installation (conditional)",
    ]

    if packs.strip():
        lines.extend(
            [
                f'    echo "> Installing packs: {packs}"',
                f"    uv run agentalloy install-packs --packs {shlex.quote(packs)}",
            ]
        )
    else:
        lines.append('    echo ">> No packs specified - skipping pack installation"')

    lines.extend(
        [
            "",
            "# Mark bootstrap complete",
            '    touch "$APP_DIR/.bootstrap-complete"',
            "fi",
            "",
            "# SIGTERM trap for graceful shutdown (only if Ollama was started)",
            'if [ -n "${OLLAMA_PID:-}" ]; then',
            '    trap "kill ${OLLAMA_PID} 2>/dev/null; exit 0" SIGTERM',
            "fi",
            "",
            "# Start uvicorn",
            'echo ">> Starting uvicorn..."',
            "exec uv run uvicorn agentalloy.app:app --host 0.0.0.0 --port 47950 --log-level info",
        ]
    )

    return "\n".join(lines) + "\n"


def _cleanup_temp_entrypoint(entrypoint: Path) -> None:
    """Remove the temporary entrypoint file.

    Idempotent — silently ignores missing files.

    Parameters
    ----------
    entrypoint : Path
        Path to the entrypoint script to remove.
    """
    if entrypoint.exists():
        entrypoint.unlink()


# ---------------------------------------------------------------------------
# Container run
# ---------------------------------------------------------------------------


def _run_container(runtime: str, entrypoint: Path, packs: str) -> int:
    """Run the agentalloy container with volumes, env, and port mapping.

    Runs ``{runtime} run --replace -d --name agentalloy`` with:

    * Volume mounts: ``agentalloy-data:/app/data`` and ``~/.ollama:/root/.ollama``
    * Env vars: ``AGENTIALLOY_PACKS``, ``ENTRYPOINT``, ``LADYBUG_DB_PATH``,
      ``DUCKDB_PATH``, ``LOG_LEVEL``
    * Port mapping: ``-p 47950:47950``

    Parameters
    ----------
    runtime : str
        Container runtime binary (e.g. ``"podman"`` or ``"docker"``).
    entrypoint : Path
        Path to the generated entrypoint script (mounted as a volume).
    packs : str
        Comma-separated list of packs to install.

    Returns
    -------
    int
        Exit code from the runtime command.
    """
    env = {
        "AGENTIALLOY_PACKS": packs,
        "ENTRYPOINT": str(entrypoint),
        "LADYBUG_DB_PATH": "/app/data/ladybug",
        "DUCKDB_PATH": "/app/data/skills.duck",
        "LOG_LEVEL": "info",
    }
    env_cmd: list[str] = []
    for k, v in env.items():
        env_cmd.extend(["-e", f"{k}={v}"])

    home = Path.home()
    cmd = [
        runtime,
        "run",
        "--replace",
        "-d",
        "--name",
        "agentalloy",
        "-p",
        "47950:47950",
        "-v",
        "agentalloy-data:/app/data",
        "-v",
        f"{home}/.ollama:/root/.ollama",
        "-v",
        f"{entrypoint}:/app/entrypoint.sh:ro",
        *env_cmd,
        "agentalloy:local",
        "/app/entrypoint.sh",
    ]

    try:
        subprocess.run(cmd, check=True, timeout=300)
        return 0
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    except subprocess.TimeoutExpired:
        _print("  [red]Container run timed out after 300s[/red]")
        return 1


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def _wait_for_health(port: int, timeout: int = 300) -> bool:
    """Poll the container's /health endpoint with exponential backoff.

    Starts with a 2-second initial interval and doubles each retry
    (2, 4, 8, 16, …) up to the given *timeout*.

    Parameters
    ----------
    port : int
        The port on which the container exposes the /health endpoint.
    timeout : int, optional
        Maximum seconds to wait (default 300).

    Returns
    -------
    bool
        True if the endpoint responds, False on timeout.
    """
    import time

    url = f"http://127.0.0.1:{port}/health"
    interval = 2
    start = time.monotonic()

    while True:
        try:
            import urllib.request

            urllib.request.urlopen(url, timeout=5)
            return True
        except OSError:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return False
            time.sleep(interval)
            interval = min(interval * 2, timeout)
