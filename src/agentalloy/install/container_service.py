"""Container-aware database lock resolution helpers.

Provides functions for detecting container environments, stopping/starting
the uvicorn service, and testing Kuzu database lock release — all needed
for the container-aware Kuzu lock resolution mechanism (TASK-1).
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path

from agentalloy.install import server_proc
from agentalloy.install import state as install_state

_DEFAULT_UVICORN_CMD = "uv run uvicorn agentalloy.app:app --host 0.0.0.0 --port 47950"


def is_in_container() -> bool:
    """Return True if the process is running inside a container.

    Detects containers by checking for the Docker sentinel file ``/.dockerenv``
    or the presence of the ``/app`` directory, consistent with
    ``agentalloy.app:app`` (line 62).
    """
    try:
        if Path("/.dockerenv").exists():
            return True
    except OSError:
        pass
    try:
        if Path("/app").is_dir():
            return True
    except OSError:
        pass
    return False


def _find_uvicorn_pid() -> int | None:
    """Scan /proc for the AgentAlloy uvicorn process.

    Returns the PID of the first match, or None if no matching process
    is found.  Only matches processes that serve ``agentalloy.app``,
    avoiding accidental kills of unrelated uvicorn instances in shared
    containers or test/debug sessions.
    """
    proc_dir = Path("/proc")
    if not proc_dir.is_dir():
        return None

    for pid_str in proc_dir.iterdir():
        if not pid_str.is_dir():
            continue
        cmdline_path = pid_str / "cmdline"
        try:
            cmdline = cmdline_path.read_bytes().decode("utf-8", errors="replace")
        except (OSError, PermissionError):
            continue
        if "agentalloy.app" in cmdline:
            try:
                return int(pid_str.name)
            except ValueError:
                continue
    return None


def _pid_alive(pid: int) -> bool:
    """Return True if ``pid`` is still running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it (e.g. different user).
        return True


def stop_service_in_container(no_restart: bool = False) -> bool:
    """Stop the running uvicorn service in a container.

    Scans ``/proc`` for a uvicorn process, sends SIGTERM, and waits up to
    15 seconds for it to exit. If it does not, escalates to SIGKILL.

    When ``no_restart`` is True, this function is a no-op (returns False)
    because the caller intends to skip the full stop/restart cycle.

    Returns ``True`` if a process was found and stopped, ``False`` if no
    uvicorn process was running (no-op).
    """
    if no_restart:
        return False
    pid = _find_uvicorn_pid()
    if pid is None:
        return False

    # SIGTERM first — graceful shutdown.
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        # Process already exited between scan and kill.
        return True
    except PermissionError:
        # Cannot signal — process may belong to another user.
        return False

    # Poll for exit up to 15 seconds.
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.2)

    # Escalate to SIGKILL.
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False

    # Brief wait for kernel to reap.
    time.sleep(0.4)
    return not _pid_alive(pid)


def restart_service_in_container(no_restart: bool = False) -> bool:
    """Restart the uvicorn service inside a container.

    Reads the configured port from install state, constructs the uvicorn
    command, spawns it as a background subprocess, then polls the
    ``/health`` endpoint for up to 30 seconds.

    When ``no_restart`` is True, this function is a no-op (returns True)
    because the caller intends to skip the restart.

    Returns ``True`` if the service became healthy (or no-op), ``False``
    otherwise.
    """
    if no_restart:
        return True
    # Build the uvicorn command from state.
    st = install_state.load_state()
    port = install_state.validate_port(st.get("port", 47950))
    cmd = f"uv run uvicorn agentalloy.app:app --host 0.0.0.0 --port {port}"

    log_path = server_proc.server_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Parse the command into a list for subprocess.Popen.
    cmd_list = cmd.split()

    # Load the user's .env file so the restarted service has the same
    # runtime configuration as the original (API keys, model settings, etc.).
    env = os.environ.copy()
    env_path = install_state.user_data_dir() / ".env"
    if env_path.is_file():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
        except OSError:
            pass

    proc: subprocess.Popen[bytes] | None = None
    started = False
    try:
        with open(log_path, "ab", buffering=0) as log_fh:
            proc = subprocess.Popen(
                cmd_list,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
        started = True
    except Exception:
        return False

    # Poll /health endpoint up to 30 seconds.
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if server_proc.port_reachable(port):
            # Verify the process is still alive (not crashed immediately).
            if proc.poll() is None:
                return True
            # Process died — fall through to cleanup.
            break
        time.sleep(0.5)

    # Cleanup on failure.
    if started:
        try:
            assert proc is not None
            proc.terminate()
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, Exception):
            with contextlib.suppress(OSError):
                proc.kill()
    return False


def test_kuzu_lock_released() -> bool:
    """Test whether the Kuzu database lock is released.

    Attempts to open a test Kuzu database connection. If it succeeds,
    the lock is released. If it fails, retries up to 5 seconds at
    0.5-second intervals.

    Returns ``True`` if the lock is released, ``False`` if still locked
    after all retries.
    """
    ladybug_path = install_state.user_data_dir() / "ladybug"
    if not ladybug_path.is_dir():
        # No database yet — not locked.
        return True

    max_retries = 10  # 5 seconds / 0.5 second intervals
    retry_interval = 0.5

    for attempt in range(max_retries):
        try:
            import kuzu

            db = kuzu.Database(str(ladybug_path))
            kuzu.Connection(db)
            # Success — lock is released.
            return True
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
            else:
                # All retries exhausted — lock still held.
                return False

    return False
