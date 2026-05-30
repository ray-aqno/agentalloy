"""``preflight`` subcommand — verify host prerequisites before any install step.

Two phases:

- ``early`` (default): host-agnostic checks that gate the rest of the
  install: Python version, ``uv`` on PATH, the ``agentalloy`` CLI on
  PATH (so the runbook LLM doesn't sail past a missing ``~/.local/bin``
  entry), XDG dirs writable, network reachable, default port free.
- ``runner``: runner-specific checks (Ollama, llama-server, FastFlowLM). Run after
  ``recommend-models`` so we know which runner was selected.

Exit codes follow the project contract (see
``agentalloy.install.__main__``):

    0  all checks passed
    1  one or more user-correctable checks failed
    2  unexpected exception (re-raised by the dispatcher)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TypedDict
from urllib.error import URLError
from urllib.request import Request, urlopen

from agentalloy.install import state as install_state
from agentalloy.install.output import add_json_flag, write_result

SCHEMA_VERSION = 1

_DEFAULT_PORT = 47950
_PHASES = ("early", "runner", "container")
_OLLAMA_PORT = 11434


def _check(
    name: str,
    *,
    passed: bool,
    started: float,
    detail: str | None = None,
    error: str | None = None,
    remediation: str | None = None,
    severity: str = "fatal",
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": name,
        "passed": passed,
        "severity": severity,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    if detail:
        out["detail"] = detail
    if error:
        out["error"] = error
    if remediation:
        out["remediation"] = remediation
    return out


# ---------------------------------------------------------------------------
# Early-phase checks
# ---------------------------------------------------------------------------


def _check_python_version() -> dict[str, Any]:
    t0 = time.monotonic()
    v = sys.version_info
    if v >= (3, 12):
        return _check(
            "python_version",
            passed=True,
            started=t0,
            detail=f"Python {v.major}.{v.minor}.{v.micro}",
        )
    return _check(
        "python_version",
        passed=False,
        started=t0,
        error=f"Python {v.major}.{v.minor}.{v.micro} < 3.12",
        remediation="Install Python 3.12+ (e.g. via mise, pyenv, or your OS package manager).",
    )


def _check_uv_present() -> dict[str, Any]:
    t0 = time.monotonic()
    binary = shutil.which("uv")
    if binary:
        return _check("uv_present", passed=True, started=t0, detail=f"uv at {binary}")
    return _check(
        "uv_present",
        passed=False,
        started=t0,
        error="uv not found on PATH",
        remediation=(
            "Install uv: see https://docs.astral.sh/uv/getting-started/installation/. "
            "Do not auto-execute the install script — confirm with the user first."
        ),
    )


def _path_entries() -> list[str]:
    return [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]


def _check_cli_on_path() -> dict[str, Any]:
    """Verify ``agentalloy`` resolves and the canonical user-bin dir is on PATH.

    The runbook hard-stops here because every later step shells out to
    ``agentalloy ...`` from the user's repo cwd; a missing PATH entry
    silently routes through ``~/.local/bin/agentalloy`` only when the
    LLM happens to use the absolute path, which it shouldn't.
    """
    t0 = time.monotonic()
    binary = shutil.which("agentalloy")
    home = Path.home()
    expected = str(home / ".local" / "bin")
    on_path = expected in _path_entries()

    if binary and on_path:
        return _check(
            "cli_on_path",
            passed=True,
            started=t0,
            detail=f"agentalloy at {binary}; {expected} on PATH",
        )

    parts: list[str] = []
    if not binary:
        parts.append("`agentalloy` not resolvable on PATH")
    if not on_path:
        parts.append(f"{expected} not in PATH")
    error = "; ".join(parts)

    remediation = (
        f"Add this line to your shell profile (~/.bashrc, ~/.zshrc) and "
        f'restart the shell:\n\n    export PATH="{expected}:$PATH"\n\n'
        f"Then re-run `agentalloy preflight`. If `uv tool install --editable .` "
        f"has not been run yet, run it first."
    )
    return _check(
        "cli_on_path",
        passed=False,
        started=t0,
        error=error,
        remediation=remediation,
    )


def _check_xdg_dirs_writable() -> dict[str, Any]:
    t0 = time.monotonic()
    config_home = (
        Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "agentalloy"
    )
    data_home = (
        Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "agentalloy"
    )

    problems: list[str] = []
    for d in (config_home, data_home):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            problems.append(f"cannot create {d}: {exc}")
            continue
        if not os.access(d, os.W_OK):
            problems.append(f"{d} not writable")

    if problems:
        return _check(
            "xdg_dirs_writable",
            passed=False,
            started=t0,
            error="; ".join(problems),
            remediation=(
                "Ensure your user owns these directories: "
                f"`chown -R $USER {config_home} {data_home}` "
                "and that the parent dirs exist."
            ),
        )
    return _check(
        "xdg_dirs_writable",
        passed=True,
        started=t0,
        detail=f"writable: {config_home}, {data_home}",
    )


def _check_network_reachable() -> dict[str, Any]:
    """HEAD https://github.com — required for model + (some) pack downloads."""
    t0 = time.monotonic()
    try:
        req = Request("https://github.com", method="HEAD")
        with urlopen(req, timeout=3) as resp:  # noqa: S310 — fixed URL
            status = getattr(resp, "status", 200)
    except (URLError, OSError) as exc:
        return _check(
            "network_reachable",
            passed=False,
            started=t0,
            severity="warn",
            error=f"HEAD https://github.com failed: {exc}",
            remediation=(
                "Check network / proxy settings. Offline installs can still "
                "complete with locally-cached models, but pack manifest "
                "downloads will fail."
            ),
        )
    return _check(
        "network_reachable",
        passed=True,
        started=t0,
        detail=f"github.com reachable (HTTP {status})",
    )


def _check_port_free(port: int) -> dict[str, Any]:
    t0 = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        return _check(
            "port_free",
            passed=False,
            started=t0,
            severity="warn",
            error=f"port {port} in use: {exc}",
            remediation=(
                f"Either stop the process bound to {port}, or pass "
                f"`--port <n>` to `agentalloy write-env` later."
            ),
        )
    finally:
        sock.close()
    return _check("port_free", passed=True, started=t0, detail=f"port {port} free")


# ---------------------------------------------------------------------------
# Runner-phase checks
# ---------------------------------------------------------------------------


def _check_ollama_present() -> dict[str, Any]:
    t0 = time.monotonic()
    binary = shutil.which("ollama")
    if binary:
        return _check("ollama_present", passed=True, started=t0, detail=f"ollama at {binary}")
    return _check(
        "ollama_present",
        passed=False,
        started=t0,
        error="ollama not found on PATH",
        remediation=(
            "Install Ollama:\n"
            "  Linux:   curl -fsSL https://ollama.com/install.sh | sh\n"
            "  macOS:   brew install ollama (or https://ollama.com/download/mac)\n"
            "  Windows: https://ollama.com/download\n"
            "Do not auto-execute — confirm with the user first."
        ),
    )


def _check_ollama_reachable() -> dict[str, Any]:
    t0 = time.monotonic()
    url = f"http://localhost:{_OLLAMA_PORT}/api/tags"
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=2) as resp:
            _ = resp.read(1)
    except (URLError, OSError) as exc:
        return _check(
            "ollama_reachable",
            passed=False,
            started=t0,
            error=f"GET {url} failed: {exc}",
            remediation=(
                "Start the Ollama daemon: `ollama serve` (Linux), or use the "
                "menubar app (macOS/Windows). Re-run preflight once "
                f"`curl -s http://localhost:{_OLLAMA_PORT}/api/tags` returns JSON."
            ),
        )
    return _check("ollama_reachable", passed=True, started=t0, detail=f"GET {url} ok")


def _try_start_ollama() -> bool:
    """Attempt to start ollama serve in the background.

    Spawns ``ollama serve &`` with output suppressed to a log file.
    Polls until reachable or times out after 15 seconds.

    Returns True if ollama became reachable.
    """
    if not shutil.which("ollama"):
        return False

    log_path = install_state.user_data_dir() / "logs" / "ollama.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_path.open("ab") as log_fh:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=log_fh,
                stderr=log_fh,
                start_new_session=True,
            )
    except OSError:
        return False

    # Poll until reachable
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", _OLLAMA_PORT), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def _check_llama_server_present() -> dict[str, Any]:
    t0 = time.monotonic()
    binary = shutil.which("llama-server")
    if binary:
        return _check(
            "llama_server_present", passed=True, started=t0, detail=f"llama-server at {binary}"
        )
    return _check(
        "llama_server_present",
        passed=False,
        started=t0,
        error="llama-server not found on PATH",
        remediation=(
            "Install llama-server (llama.cpp): see "
            "https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md"
            "You can also build it from source or use a pre-built binary.\\n"
            "Do not auto-execute — confirm with the user first."
        ),
    )


def _check_llama_server_reachable() -> dict[str, Any]:
    t0 = time.monotonic()
    url = "http://localhost:11436/api/tags"
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=2) as resp:
            _ = resp.read(1)
    except (URLError, OSError) as exc:
        return _check(
            "llama_server_reachable",
            passed=False,
            started=t0,
            error=f"GET {url} failed: {exc}",
            remediation=(
                "Start the llama-server daemon: `llama-server --embeddings --port 11436` "
                "or ensure it's running. Re-run preflight once "
                "`curl -s http://localhost:11436/api/tags` returns JSON."
            ),
        )
    return _check("llama_server_reachable", passed=True, started=t0, detail=f"GET {url} ok")


def _check_fastflowlm_present() -> dict[str, Any]:
    t0 = time.monotonic()
    binary = shutil.which("flm")
    if binary:
        return _check("fastflowlm_present", passed=True, started=t0, detail=f"flm at {binary}")
    return _check(
        "fastflowlm_present",
        passed=False,
        started=t0,
        error="flm not found on PATH",
        remediation="Install FastFlowLM and ensure `flm` is on PATH.",
    )


# ---------------------------------------------------------------------------
# Container-phase checks
# ---------------------------------------------------------------------------


class _ComposeProbe(TypedDict):
    """Per-binary probe result. ``stderr`` is empty unless ``compose`` failed."""

    binary: str
    path: str | None
    compose_ok: bool
    stderr: str


def _probe_compose_runtime() -> tuple[str | None, str | None, list[_ComposeProbe]]:
    """Probe podman and docker for a working ``compose`` subcommand.

    Returns ``(label, binary_path, probes)``. ``label`` and ``binary_path``
    are populated for the first runtime whose ``compose version`` exits 0
    (podman preferred, docker fallback). ``probes`` records every candidate
    we considered — including ones we found on PATH but that lacked a working
    compose provider — so callers can build accurate error messages.
    """
    probes: list[_ComposeProbe] = []
    chosen_label: str | None = None
    chosen_path: str | None = None
    for candidate in ("podman", "docker"):
        binary = shutil.which(candidate)
        if binary is None:
            probes.append({"binary": candidate, "path": None, "compose_ok": False, "stderr": ""})
            continue
        stderr = ""
        compose_ok = False
        try:
            result = subprocess.run(
                [binary, "compose", "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            compose_ok = result.returncode == 0
            if not compose_ok:
                stderr = (result.stderr or result.stdout or "").strip()
        except (subprocess.TimeoutExpired, OSError) as exc:
            stderr = str(exc)
        probes.append(
            {
                "binary": candidate,
                "path": binary,
                "compose_ok": compose_ok,
                "stderr": stderr,
            }
        )
        if compose_ok and chosen_label is None:
            chosen_label = f"{candidate} compose"
            chosen_path = binary
    return chosen_label, chosen_path, probes


def _detect_compose_binary() -> tuple[str | None, str | None]:
    """Detect a compose-capable binary (podman preferred, docker fallback).

    Returns ``(label, binary_path)`` where:
      - ``label`` is ``"podman compose"`` or ``"docker compose"`` (for display/state)
      - ``binary_path`` is the absolute path to the main binary (e.g. ``/usr/bin/podman``)

    Returns ``(None, None)`` if neither found.
    """
    label, binary_path, _ = _probe_compose_runtime()
    return label, binary_path


def _compose_failure_message(probes: list[_ComposeProbe]) -> tuple[str, str]:
    """Build (error, remediation) strings describing why no compose is available.

    Distinguishes three states:
      (a) neither binary present on PATH,
      (b) at least one binary present but its ``compose`` subcommand failed
          (typically: provider plugin missing — ``podman-compose`` /
          ``docker-compose`` not installed),
      (c) handled by the caller — at least one probe succeeded.
    """
    present = [p for p in probes if p["path"] is not None]
    if not present:
        return (
            "Neither `podman` nor `docker` found on PATH",
            (
                "Install Podman (recommended) or Docker:\n"
                "  Linux:   sudo apt install podman podman-compose\n"
                "  macOS:   brew install podman\n"
                "  Verify:  podman compose version (or docker compose version)"
            ),
        )
    # State (b): binary present but `compose` subcommand failed.
    lines = [
        f"{p['binary']} found at {p['path']} but `{p['binary']} compose version` failed"
        + (f": {p['stderr']}" if p["stderr"] else "")
        for p in present
    ]
    error = "Container runtime present but no compose provider:\n  " + "\n  ".join(lines)
    has_podman = any(p["binary"] == "podman" for p in present)
    has_docker = any(p["binary"] == "docker" for p in present)
    remediation_lines = ["Install a compose provider for your runtime:"]
    if has_podman:
        remediation_lines.append(
            "  podman: sudo apt install podman-compose  (or: pip install podman-compose)"
        )
    if has_docker:
        remediation_lines.append(
            "  docker: sudo apt install docker-compose-plugin  (or: docker-compose)"
        )
    remediation_lines.append("Then verify: podman compose version (or docker compose version)")
    return error, "\n".join(remediation_lines)


def _check_git_present() -> dict[str, Any]:
    """Container install clones the agentalloy repo into a cache dir when the
    user runs setup without a local checkout (the Containerfile build context
    needs the full source tree). That clone needs git on PATH; surface a
    clear error here rather than letting the clone subprocess crash later.
    """
    t0 = time.monotonic()
    git_path = shutil.which("git")
    if git_path:
        return _check(
            "git_present",
            passed=True,
            started=t0,
            detail=f"git at {git_path}",
        )
    return _check(
        "git_present",
        passed=False,
        started=t0,
        error="git not found on PATH",
        remediation=(
            "Install git (e.g. `apt install git`, `brew install git`, "
            "`dnf install git`). The container install clones the agentalloy "
            "repo into ~/.cache/agentalloy/repo for the build context."
        ),
    )


def _check_compose_binary() -> dict[str, Any]:
    t0 = time.monotonic()
    label, binary_path, probes = _probe_compose_runtime()
    if label is not None:
        return _check(
            "compose_binary",
            passed=True,
            started=t0,
            detail=f"{label} at {binary_path}",
        )
    error, remediation = _compose_failure_message(probes)
    return _check(
        "compose_binary",
        passed=False,
        started=t0,
        error=error,
        remediation=remediation,
    )


def _check_compose_file_present(compose_file: str | None) -> dict[str, Any]:
    t0 = time.monotonic()
    if compose_file is None:
        return _check(
            "compose_file_present",
            passed=False,
            started=t0,
            error="No compose file specified",
            remediation="Pass --compose-file <path> or select a compose file interactively.",
        )
    fp = Path(compose_file)
    if fp.exists():
        return _check(
            "compose_file_present",
            passed=True,
            started=t0,
            detail=f"compose file at {fp}",
        )
    return _check(
        "compose_file_present",
        passed=False,
        started=t0,
        error=f"Compose file not found: {fp}",
        remediation="Ensure the compose YAML file exists at the specified path.",
    )


def _check_image_build_deps(compose_file: str | None) -> dict[str, Any]:
    """Check that a Containerfile exists next to the compose file."""
    t0 = time.monotonic()
    if compose_file is None:
        return _check(
            "image_build_deps",
            passed=True,
            started=t0,
            severity="warn",
            detail="No compose file specified — skipping Containerfile check",
        )
    compose_dir = Path(compose_file).parent
    containerfile = compose_dir / "Containerfile"
    if containerfile.exists():
        return _check(
            "image_build_deps",
            passed=True,
            started=t0,
            detail=f"Containerfile at {containerfile}",
        )
    # Also check Dockerfile as fallback
    dockerfile = compose_dir / "Dockerfile"
    if dockerfile.exists():
        return _check(
            "image_build_deps",
            passed=True,
            started=t0,
            detail=f"Dockerfile at {dockerfile}",
        )
    return _check(
        "image_build_deps",
        passed=False,
        started=t0,
        error=f"No Containerfile or Dockerfile found in {compose_dir}",
        remediation="Place a Containerfile (or Dockerfile) in the same directory as your compose YAML.",
    )


# ---------------------------------------------------------------------------
# Phase orchestration
# ---------------------------------------------------------------------------


def _runner_from_models_output() -> str | None:
    """Read the chosen runner from recommend-models.json, if present."""
    fp = install_state.outputs_dir() / "recommend-models.json"
    if not fp.exists():
        return None
    try:
        data = json.loads(fp.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("selected_runner") or data.get("embed_runner") or data.get("runner")


def run_preflight(
    *,
    phase: str = "early",
    runner: str | None = None,
    port: int = _DEFAULT_PORT,
    compose_file: str | None = None,
) -> dict[str, Any]:
    if phase not in _PHASES:
        raise ValueError(f"invalid phase {phase!r}; must be one of {_PHASES}")

    t0 = time.monotonic()
    checks: list[dict[str, Any]] = []

    if phase == "early":
        checks.append(_check_python_version())
        checks.append(_check_uv_present())
        checks.append(_check_cli_on_path())
        checks.append(_check_xdg_dirs_writable())
        checks.append(_check_network_reachable())
        checks.append(_check_port_free(port))
    elif phase == "container":
        checks.append(_check_compose_binary())
        checks.append(_check_git_present())
        checks.append(_check_compose_file_present(compose_file))
        checks.append(_check_port_free(port))
        checks.append(_check_image_build_deps(compose_file))
    else:  # runner
        chosen = runner or _runner_from_models_output()
        if chosen is None:
            checks.append(
                _check(
                    "runner_selected",
                    passed=False,
                    started=t0,
                    error=(
                        "no runner specified and recommend-models output "
                        "not found at "
                        f"{install_state.outputs_dir() / 'recommend-models.json'}"
                    ),
                    remediation=(
                        "Run `agentalloy recommend-models` first, or pass "
                        "`--runner <ollama|llama-server|fastflowlm>` explicitly."
                    ),
                )
            )
        elif chosen == "ollama":
            checks.append(_check_ollama_present())
            reachable = _check_ollama_reachable()
            if not reachable["passed"]:
                # Offer to start ollama automatically
                started = _try_start_ollama()
                if started:
                    # Re-check after starting
                    reachable = _check_ollama_reachable()
            checks.append(reachable)
        elif chosen == "llama-server":
            checks.append(_check_llama_server_present())
            # _check_llama_server_reachable omitted: llama-server is started by
            # start-embed-server (later in the pipeline), not pre-running like ollama.
        elif chosen == "fastflowlm":
            checks.append(_check_fastflowlm_present())
        else:
            checks.append(
                _check(
                    "runner_supported",
                    passed=True,
                    started=t0,
                    severity="warn",
                    detail=(
                        f"runner {chosen!r} has no preflight coverage "
                        "(manual-pull runner: LM Studio, MLX, vLLM)"
                    ),
                )
            )

    fatal_failed = [c for c in checks if not c["passed"] and c.get("severity", "fatal") == "fatal"]
    warn_failed = [c for c in checks if not c["passed"] and c.get("severity") == "warn"]

    return {
        "schema_version": SCHEMA_VERSION,
        "action": "preflight" if not fatal_failed else "preflight_failed",
        "phase": phase,
        "runner": runner if phase == "runner" else None,
        "all_checks_passed": not fatal_failed and not warn_failed,
        "fatal_failures": [c["name"] for c in fatal_failed],
        "warn_failures": [c["name"] for c in warn_failed],
        "checks": checks,
        "duration_ms": int((time.monotonic() - t0) * 1000),
    }


# ---------------------------------------------------------------------------
# Subcommand interface
# ---------------------------------------------------------------------------


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],  # pyright: ignore[reportPrivateUsage]
) -> None:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "preflight",
        help=(
            "Verify host prerequisites (uv, PATH, network, runner) before "
            "running install steps. Run this first, every time."
        ),
    )
    p.add_argument(
        "--phase",
        choices=_PHASES,
        default="early",
        help="Which phase of checks to run (default: early).",
    )
    p.add_argument(
        "--runner",
        default=None,
        help=(
            "Runner-phase only: which runner to validate. If omitted, read "
            "from recommend-models.json output."
        ),
    )
    p.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_PORT,
        help=f"Port to test for availability (default: {_DEFAULT_PORT}).",
    )
    p.add_argument(
        "--compose-file",
        default=None,
        help="Container phase: path to the compose YAML file.",
    )
    add_json_flag(p)
    p.set_defaults(func=_run)


def _render_human(result: dict[str, Any]) -> None:
    """Render preflight check results in human-readable format."""
    from agentalloy.install.output import render_checklist

    phase = result.get("phase", "early")
    render_checklist(result, title=f"Preflight ({phase})")

    # Print a warning if there were non-fatal issues
    warns = [c for c in result["checks"] if not c["passed"] and c.get("severity") == "warn"]
    if warns:
        from agentalloy.install.output import print_rich

        print_rich()
        print_rich(f"  [yellow]{len(warns)} warning(s) — non-fatal, install can proceed.[/yellow]")


def _run(args: argparse.Namespace) -> int:
    result = run_preflight(
        phase=args.phase,
        runner=args.runner,
        port=args.port,
        compose_file=getattr(args, "compose_file", None),
    )
    install_state.save_output_file(result, f"preflight-{args.phase}.json")
    write_result(result, args, human_fn=_render_human)

    # Return non-zero if any fatal checks failed
    fatal = [
        c for c in result["checks"] if not c["passed"] and c.get("severity", "fatal") == "fatal"
    ]
    return 1 if fatal else 0
