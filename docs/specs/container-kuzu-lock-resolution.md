# Container Kuzu Lock Resolution

## Problem Statement

When the agentalloy container is running, the FastAPI app holds the Kuzu (LadybugDB)
database open at `/app/data/ladybug` for the lifetime of the container. Any CLI
command executed via `podman exec` that also needs to open the same database --
such as `agentalloy reembed` or `agentalloy install-packs` -- fails with:

```
RuntimeError: IO exception: Could not set lock on file : /app/data/ladybug
```

This is because Kuzu uses a file-level lock and does not support concurrent access
from multiple processes. The same lock applies to DuckDB (vector store at
`/app/data/skills.duck`).

This blocks users from adding skills or re-embedding after the container is already
running -- a critical post-setup workflow.

## Goals

- Users can run `podman exec -it agentalloy uv run agentalloy reembed` while the
  service is running, and it succeeds without database lock errors.
- Users can run `podman exec -it agentalloy uv run agentalloy install-packs` while
  the service is running, and it succeeds.
- The service is temporarily unavailable during the operation (graceful stop/restart),
  which is acceptable for admin commands.
- Clear error messaging if the stop/restart cannot succeed.

## Non-Goals

- Zero-downtime operations (reembed and install-packs are admin commands that
  inherently require exclusive DB access).
- Multi-process Kuzu support (Kuzu itself does not support this; see
  https://docs.kuzudb.com/concurrency).
- Native install (systemd/launchd) service management -- that already works.
- API-based alternatives for reembed/install-packs (out of scope for this fix;
  those would require new API endpoints).

## Current State

### How the lock occurs

1. `app.py:64-65` -- The FastAPI lifespan opens `LadybugStore` and `VectorStore`
   at startup and keeps them open for the container lifetime.
2. `ladybug.py:40` -- `kuzu.Database(self._db_path)` acquires a file lock on the
   database directory.
3. Any second process calling `kuzu.Database()` on the same path gets a lock error.

### Affected CLI commands (all open LadybugStore)

- `agentalloy reembed` -- reembed CLI at `reembed/cli.py:521`
- `agentalloy install-packs` -- calls `agentalloy.ingest` per skill, which opens
  LadybugStore at `ingest.py:196`
- `agentalloy ingest` -- opens LadybugStore at `ingest.py:196,337`
- `agentalloy authoring qa` / `authoring run` -- opens LadybugStore at
  `authoring/__main__.py:145,169`
- `agentalloy fixtures` -- opens LadybugStore at `fixtures/__main__.py:24`
- `agentalloy migrate` -- opens LadybugStore at `migrate.py:26`

### Existing mitigation (native install only)

`reembed/cli.py:491-508` -- The reembed CLI already stops systemd/launchd services
before opening the DB, then restarts them after. This works for native installs but
does NOT handle the container case. The detection logic (`_detect_service_manager`)
returns `None` inside a container, so the stop/restart is skipped silently.

### Setup wizard workaround

`simple_setup.py:1236-1246` -- During initial container setup, the wizard runs
`install-packs` in a one-shot container BEFORE starting the main service, avoiding
the lock entirely. This only works during initial setup, not for post-setup
operations.

## Desired State

When running inside the agentalloy container, CLI commands that need exclusive
database access should:

1. Detect they are inside the container.
2. Stop the running uvicorn process (PID 1 or the uvicorn subprocess).
3. Wait for the database lock to be released.
4. Perform the database operation.
5. Restart the uvicorn process.
6. Wait for the service to become healthy again.

If the service is NOT running (e.g., the container was started but the app failed
to start), the command should proceed directly without attempting to stop/restart.

## Requirements

- [REQ-1] Container detection: Commands must detect when running inside the
  agentalloy container (check for `/.dockerenv` or `/app` directory, consistent
  with existing detection in `app.py:62`).

- [REQ-2] Service process detection: When inside the container, find the uvicorn
  process PID. The container CMD is
  `uv run uvicorn agentalloy.app:app --host 0.0.0.0 --port 47950`, which may run
  as PID 1 (if the container was started with this CMD) or as a child process.
  Detection should use `ps` or `/proc` to find the uvicorn process.

- [REQ-3] Graceful stop: Send SIGTERM to the uvicorn process, wait up to 15s for
  it to exit. If it does not exit, escalate to SIGKILL. This mirrors the existing
  `server_proc.stop()` pattern.

- [REQ-4] Lock release verification: After stopping the service, verify the
  database lock is released by attempting to open a test Kuzu connection. If the
  lock is still held (e.g., the process crashed but the OS hasn't released the
  lock), wait a short period (up to 5s) and retry. If still locked, abort with a
  clear error message.

- [REQ-5] Service restart: After the database operation completes, restart the
  uvicorn process with the same command line that was originally used. Wait up to
  30s for the service to become healthy (poll `/health` endpoint).

- [REQ-6] Idempotency: If the service is already stopped when the command runs,
  the command should proceed directly without error (no-op stop, no-op restart).

- [REQ-7] User-facing messaging: Print clear status messages:
  - "Stopping agentalloy service (container mode) to release database locks..."
  - "Service stopped, proceeding with operation..."
  - "Operation complete, restarting agentalloy service..."
  - "Service restarted successfully."
  - "ERROR: Failed to restart service after operation. Run `podman restart agentalloy` manually."

- [REQ-8] Scope: Apply the container-aware stop/restart logic to ALL CLI commands
  that open LadybugStore with exclusive access. Minimum set:
  - `agentalloy reembed`
  - `agentalloy install-packs`
  - `agentalloy ingest`

  Other commands (`authoring qa`, `authoring run`, `fixtures`, `migrate`) should
  be considered for future inclusion but are not required for this fix.

- [REQ-9] --no-restart flag: The reembed CLI already has `--no-restart`. This
  should also suppress the container restart step. A new `--no-restart` flag should
  be added to `install-packs` and `ingest` for consistency.

- [REQ-10] Shared helper: The container stop/restart logic should live in a shared
  module (e.g., `agentalloy.install.container_service.py`) rather than being
  duplicated in each CLI command. This module should provide:
  - `is_in_container() -> bool`
  - `stop_service_in_container() -> bool` (returns True if something was stopped)
  - `restart_service_in_container() -> bool` (returns True if restart succeeded)

## Constraints

- The container runs as a rootless podman container, so process management may
  have limited capabilities.
- The uvicorn process may be PID 1 in the container (if started directly via
  `podman run`) or a child process (if started via compose with an entrypoint
  wrapper). Both cases must be handled.
- The container data directory `/app/data` is a named volume mount. Database
  files persist across container restarts.
- Kuzu's file lock is released when the `kuzu.Database` object is garbage
  collected or when the process exits. The lifespan's `finally` block in
  `app.py:157` calls `store.close()`, but this may not release the file lock
  immediately -- the process must fully exit.

## Edge Cases

- **Container started but service failed**: If the container is running but
  uvicorn is not (e.g., it crashed), the stop step is a no-op and the command
  proceeds normally. The restart step should still attempt to start the service.

- **Multiple concurrent `podman exec` commands**: If two CLI commands are
  started simultaneously, both will try to stop the service. The first to
  acquire the DB lock wins; the second will fail. This is acceptable --
  concurrent admin operations are not a supported pattern.

- **User interrupt (Ctrl+C)**: If the user interrupts the command during the
  database operation, the service should still be restarted in a `finally` block,
  matching the existing reembed pattern (`reembed/cli.py:601-602`).

- **Service restart fails**: If the restart fails (e.g., port conflict, out of
  memory), the command should still return the exit code from the database
  operation, but print a clear warning that the service needs manual restart.

- **Different container runtime**: The fix should work for both Podman and Docker
  (the compose.yaml is explicitly cross-compatible).

## Success Criteria

1. `podman exec -it agentalloy uv run agentalloy reembed` succeeds when the
   agentalloy service is running in the container.
2. `podman exec -it agentalloy uv run agentalloy install-packs --packs all`
   succeeds when the agentalloy service is running in the container.
3. After the command completes, the agentalloy service is back up and responding
   to `/health`.
4. Running the same commands when the service is NOT running (e.g., container
   started with a different CMD) still works without error.
5. No regression in native install (systemd/launchd) service management.
6. Existing tests in `tests/test_reembed.py` for service stop/restart continue
   to pass.
