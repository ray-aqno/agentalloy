# Container Kuzu Lock Resolution — Design Document

## 1. Overview

When the agentalloy container is running, the FastAPI lifespan in `app.py` holds the
Kuzu (LadybugDB) database open for the container lifetime. Any CLI command executed via
`podman exec` that opens the same database — `reembed`, `install-packs`, `ingest` — fails
with:

    RuntimeError: IO exception: Could not set lock on file : /app/data/ladybug

This design adds a **container-aware stop/restart mechanism** so CLI commands can
temporarily stop the uvicorn process, perform exclusive DB access, then restart the
service.

## 2. Architecture

### 2.1 Shared Module: `agentalloy.install.container_service`

A new helper module at `src/agentalloy/install/container_service.py` provides three
public functions:

```
is_in_container()        -> bool
stop_service_in_container() -> bool   # returns True if something was stopped
restart_service_in_container() -> bool  # returns True if restart succeeded
```

This module is shared across all CLI commands that need container-aware DB access,
avoiding duplication.

### 2.2 Process Detection Strategy

Two container run modes must be handled:

- **Direct podman run** (CMD = uvicorn): The uvicorn process is PID 1 in the container.
- **Podman compose** (entrypoint wrapper): The entrypoint script is PID 1; uvicorn is a
  child process.

Detection algorithm:

1. Search `/proc` for any process whose command line contains `uvicorn` and
   `agentalloy.app`.
2. If found, return the PID.
3. If multiple matches (e.g., `uvicorn ... --reload` spawning workers), pick the
   parent (lowest PID) to ensure graceful shutdown.
4. If no match found, the service is not running — treat as no-op.

This avoids depending on `ps` output format (which varies between distros) and reads
the canonical `/proc` filesystem directly.

### 2.3 Stop Procedure

1. Send SIGTERM to the detected uvicorn PID.
2. Poll up to 15 seconds, checking `/proc/<pid>/status` for process exit.
3. If the process is still alive after 15s, escalate to SIGKILL.
4. Return `True` if the process was found and stopped, `False` if nothing was running.

This mirrors the existing `server_proc.stop()` pattern (SIGTERM -> 10s wait -> SIGKILL),
extended to 15s for container environments where graceful shutdown may take longer.

### 2.4 Lock Release Verification

After stopping, the Kuzu file lock must be verified as released:

1. Attempt to open a test Kuzu `Database` connection to the same path.
2. If the lock is still held (the process crashed but the OS hasn't released it),
   wait up to 5 seconds total (with 500ms intervals) and retry.
3. If still locked after 5s, abort with a clear error message.
4. Close the test connection immediately after verification.

This is critical because `kuzu.Database` file locks are released when the process exits,
but the kernel may take a moment to fully release the file descriptor.

### 2.5 Restart Procedure

1. Reconstruct the uvicorn command line from the configured host/port (read from
   install state via `install_state.load_state()`).
2. Spawn uvicorn as a background child process using `subprocess.Popen`.
3. Poll the `/health` endpoint via `httpx` (or raw TCP connect) up to 30 seconds.
4. Return `True` if healthy, `False` if timeout.

The restart uses the same env-loading logic as `server_proc.start_background()` to
ensure the child process has the correct `.env` configuration.

### 2.6 User Messaging

Clear, actionable messages at each step (REQ-7):

```
[agentalloy] Stopping agentalloy service (container mode) to release database locks...
[agentalloy] Service stopped, proceeding with operation...
[agentalloy] Operation complete, restarting agentalloy service...
[agentalloy] Service restarted successfully.
[agentalloy] WARNING: Failed to restart service after operation.
             Run `podman restart agentalloy` manually.
```

All messages are printed to stderr so they don't interfere with JSON output from
install-packs.

## 3. Requirement Coverage

### REQ-1: Container Detection

**Implementation**: `is_in_container()` checks `Path("/.dockerenv").exists()` or
`Path("/app").is_dir()`, identical to the pattern in `app.py:62`.

**Rationale**: Consistent with existing detection; both Podman and Docker create
`/.dockerenv` (Podman may not in rootless mode, so `/app` directory check is the
fallback).

### REQ-2: Service Process Detection

**Implementation**: `/proc` scanning as described in Section 2.2. Handles both:
- PID 1 direct case (uvicorn IS PID 1)
- Child process case (entrypoint is PID 1, uvicorn is child)

**Rationale**: `/proc` is available in all Linux containers, including rootless Podman.
Parsing `/proc/<pid>/cmdline` is more reliable than `ps` output.

### REQ-3: Graceful Stop

**Implementation**: SIGTERM -> poll 15s -> SIGKILL escalation, matching the existing
`server_proc.stop()` pattern.

**Rationale**: Graceful stop allows uvicorn to finish in-flight requests and close
connections cleanly before releasing the DB lock.

### REQ-4: Lock Release Verification

**Implementation**: Test Kuzu connection after stop, retry up to 5s if locked.

**Rationale**: Prevents race conditions where the process has exited but the OS
hasn't fully released the file lock yet.

### REQ-5: Service Restart

**Implementation**: Spawn uvicorn with the same config, poll `/health` endpoint up to
30s.

**Rationale**: The `/health` endpoint is the standard readiness check used by the
FastAPI app; it confirms the full lifespan (including DB open) has completed.

### REQ-6: Idempotency

**Implementation**:
- `stop_service_in_container()` returns `False` if no uvicorn process found — caller
  proceeds without error.
- `restart_service_in_container()` returns `False` if the service was never running
  (or was already stopped) — caller prints a warning but doesn't fail.

**Rationale**: The container might be running with a different CMD (e.g., a shell)
or the service might have crashed before the CLI command runs.

### REQ-7: User-Facing Messaging

**Implementation**: All status messages printed to stderr with `[agentalloy]` prefix
for easy grepping. Error messages include manual remediation steps.

### REQ-8: Scope

**Implementation**: The container stop/restart logic is called from:
1. `reembed/cli.py` — replaces the existing `_is_service_running()` + `_stop_service()`
   path when inside a container.
2. `install/subcommands/install_packs.py` — wraps `_bulk_reembed()` with container
   stop/restart.
3. `ingest.py` — wraps the `LadybugStore` open with container stop/restart.

### REQ-9: --no-restart Flag

**Implementation**:
- `reembed/cli.py`: The existing `--no-restart` flag is extended to suppress BOTH
  systemd/launchd restart AND container restart.
- `install-packs`: A new `--no-restart` flag is added to the argparse subparser.
- `ingest`: A new `--no-restart` flag is added to the argparse subparser.

The flag is forwarded through the call chain: `install-packs` -> `_bulk_reembed()` ->
`reembed_main()` so a single `--no-restart` prevents all restart attempts.

### REQ-10: Shared Helper Module

**Implementation**: All container stop/restart logic lives in
`agentalloy.install.container_service`. Each CLI command imports and calls the
three public functions. No duplication.

## 4. Integration Points

### 4.1 reembed/cli.py

The existing service management (`_detect_service_manager`, `_is_service_running`,
`_stop_service`, `_restart_service`) is extended:

```python
from agentalloy.install.container_service import (
    is_in_container,
    stop_service_in_container,
    restart_service_in_container,
)

def _is_service_running() -> bool:
    """Check service via native service manager OR container detection."""
    # Existing systemd/launchd check...
    # NEW: If in container, check for uvicorn process
    if is_in_container():
        return _find_uvicorn_pid() is not None
    return _native_is_running()

def _stop_service() -> bool:
    """Stop service via native manager OR container."""
    if is_in_container():
        return stop_service_in_container()
    return _native_stop()

def _restart_service():
    """Restart service via native manager OR container."""
    if is_in_container():
        restart_service_in_container()
    else:
        _native_restart()
```

The `--no-restart` flag already suppresses `_restart_service()` — no changes needed
to the flag semantics.

### 4.2 install-packs

The `_bulk_reembed()` function is wrapped:

```python
def _bulk_reembed(no_restart: bool = False) -> int:
    from agentalloy.install.container_service import (
        is_in_container,
        stop_service_in_container,
        restart_service_in_container,
    )

    container_stopped = False
    if is_in_container():
        container_stopped = stop_service_in_container()
        print("[agentalloy] Service stopped, proceeding with reembed...")

    try:
        rc = reembed_main(["--no-restart"])  # reembed handles its own restart
    finally:
        if container_stopped and not no_restart:
            print("[agentalloy] Reembed complete, restarting service...")
            if not restart_service_in_container():
                print("[agentalloy] WARNING: Failed to restart service...")

    return rc
```

### 4.3 ingest

The `ingest.py` `_single()` and `_batch()` functions are wrapped similarly:

```python
from agentalloy.install.container_service import (
    is_in_container,
    stop_service_in_container,
    restart_service_in_container,
)

def _single(yaml_path, *, force, yes, strict, no_restart=False):
    container_stopped = False
    if is_in_container():
        container_stopped = stop_service_in_container()

    try:
        # existing ingest logic...
        pass
    finally:
        if container_stopped and not no_restart:
            restart_service_in_container()
```

## 5. Module Structure

```
src/agentalloy/install/
  container_service.py        # NEW: shared container stop/restart helpers
  __init__.py
  __main__.py
  server_proc.py              # existing: native service management
  state.py                    # existing: install state management
  subcommands/
    install_packs.py          # MODIFIED: add --no-restart, wrap _bulk_reembed
    reembed.py                # MODIFIED: forward --no-restart flag
    simple_setup.py           # no changes needed (uses one-shot container)
```

## 6. Error Handling

### 6.1 Service Not Running
- `stop_service_in_container()` returns `False` -> command proceeds normally.
- `restart_service_in_container()` is skipped -> no error.

### 6.2 Stop Timeout
- After 15s SIGTERM + SIGKILL, if the process is still alive, print an error and
  abort the operation. The DB lock cannot be released.

### 6.3 Lock Verification Failure
- After 5s of retries, if the Kuzu lock is still held, print an error with the
  process state and abort. Suggest `podman exec agentalloy kill <pid>` as remediation.

### 6.4 Restart Failure
- Print a clear warning with manual remediation instructions.
- The CLI command's exit code reflects the DB operation result, not the restart
  failure (matching the existing reembed pattern where FTS failure is non-fatal).

### 6.5 User Interrupt (Ctrl+C)
- The `finally` block in each CLI command ensures `restart_service_in_container()`
  is called even on interrupt, matching `reembed/cli.py:601-602`.

## 7. Edge Cases

### 7.1 Container Started but Service Failed
The process detection finds no uvicorn process. Stop is a no-op. The command
proceeds directly. After the operation, restart attempts to start uvicorn from
the configured host/port.

### 7.2 Concurrent podman exec Commands
Two commands may both detect the service as running and try to stop it. The first
to send SIGTERM wins; the second will find the process gone (no-op stop) and
proceed. If both try to restart simultaneously, one will fail (port in use) and
the other will succeed. This is acceptable per the spec.

### 7.3 Different Container Runtime
The fix works for both Podman and Docker because:
- Container detection is runtime-agnostic (checks `/.dockerenv` and `/app`).
- Process management uses `/proc` and POSIX signals, not runtime-specific APIs.
- Health check uses HTTP, not runtime-specific APIs.

### 7.4 PID 1 as Entrypoint Wrapper
If the container uses a compose entrypoint script (e.g., `docker-entrypoint.sh`)
that launches uvicorn as a child, the `/proc` scan finds the uvicorn process
regardless of its PID number. The entrypoint script (PID 1) is not the target
of SIGTERM — only the uvicorn process is.

## 8. Testing Strategy

See `container-kuzu-lock-resolution-tests.md` for the complete test plan.

Summary of test categories:
1. **Unit tests** for `container_service.py` (container detection, stop, restart)
2. **Integration tests** for reembed/install-packs/ingest with mocked container
3. **Edge case tests** (not running, concurrent, interrupt, failure)
4. **Regression tests** ensuring existing native install paths are unchanged

## 9. Files to Create/Modify

### New files:
- `src/agentalloy/install/container_service.py` — shared container helpers
- `tests/test_container_service.py` — unit tests

### Modified files:
- `src/agentalloy/reembed/cli.py` — extend `_is_service_running()`, `_stop_service()`,
  `_restart_service()` to handle container mode
- `src/agentalloy/install/subcommands/install_packs.py` — add `--no-restart` flag,
  wrap `_bulk_reembed()` with container stop/restart
- `src/agentalloy/install/subcommands/reembed.py` — forward `--no-restart` flag
- `src/agentalloy/ingest.py` — add `--no-restart` flag, wrap DB access with
  container stop/restart

## 10. Implementation Phases

### Phase 1: Shared Module
Create `container_service.py` with `is_in_container()`, `stop_service_in_container()`,
`restart_service_in_container()`, and `verify_lock_released()`. Write unit tests.

### Phase 2: reembed Integration
Extend `reembed/cli.py` service management functions to use the container helpers
when `is_in_container()` is true.

### Phase 3: install-packs & ingest Integration
Add `--no-restart` flag to install-packs and ingest subcommands. Wrap their DB
access with container stop/restart.

### Phase 4: End-to-End Testing
Run integration tests in a container environment (podman) to verify the full flow.
