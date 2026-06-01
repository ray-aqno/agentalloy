# Container Kuzu Lock Resolution — Kanban Build Tasks

Branch: `feature/container-kuzu-lock-resolution-design`

---

## TASK-1: Container Service Module (Phase 1)

### Description
Create the shared container-aware service management module. This is the foundational
building block — all other tasks depend on it. The module provides three public functions
that detect whether the CLI is running inside a container, stop the uvicorn service,
and restart it.

### Files to Create
- `src/agentalloy/install/container_service.py` (new)

### Implementation Details

**is_in_container() -> bool**
- Check `Path("/.dockerenv").exists()` OR `Path("/app").is_dir()`
- Matches the pattern in `app.py:62`

**_find_uvicorn_pid() -> int | None**
- Scan `/proc/<pid>/cmdline` for processes containing both "uvicorn" and "agentalloy.app"
- If multiple matches (e.g., --reload workers), return the parent (lowest PID)
- Returns None if no match found

**stop_service_in_container() -> bool**
- Call `_find_uvicorn_pid()`
- If found: send SIGTERM, poll `/proc/<pid>/status` for up to 15s
- If still alive after 15s: escalate to SIGKILL
- Return True if process was found and stopped, False if nothing was running

**verify_lock_released(db_path: str) -> bool**
- Attempt to open a test Kuzu `Database` connection to `db_path`
- If lock still held, wait up to 5s total (500ms intervals) and retry
- Return True if lock released, False if timeout

**restart_service_in_container() -> bool**
- Read host/port from `install_state.load_state()`
- Reconstruct uvicorn command line
- Spawn uvicorn via `subprocess.Popen`
- Poll `/health` endpoint via `httpx` up to 30s
- Return True if healthy, False if timeout

**User messaging (all to stderr)**
- `[agentalloy] Stopping agentalloy service (container mode) to release database locks...`
- `[agentalloy] Service stopped, proceeding with operation...`
- `[agentalloy] Operation complete, restarting agentalloy service...`
- `[agentalloy] Service restarted successfully.`
- `[agentalloy] WARNING: Failed to restart service after operation.`

### Acceptance Criteria
- [ ] Module imports cleanly: `from agentalloy.install.container_service import is_in_container, stop_service_in_container, restart_service_in_container`
- [ ] `is_in_container()` returns correct values in container and non-container contexts
- [ ] `_find_uvicorn_pid()` correctly identifies uvicorn processes via /proc scanning
- [ ] `stop_service_in_container()` sends SIGTERM, escalates to SIGKILL after 15s
- [ ] `verify_lock_released()` retries Kuzu open up to 5s on lock contention
- [ ] `restart_service_in_container()` spawns uvicorn and polls /health up to 30s
- [ ] All functions are idempotent (safe to call when nothing is running)
- [ ] Error messages include manual remediation steps (REQ-7)

### TDD Instructions
1. Write `tests/test_container_service.py` first (see test plan for test cases DC-1 through DC-5, PD-1 through PD-5, SS-1 through SS-7, LV-1 through LV-4, SR-1 through SR-5)
2. Run tests — they should fail
3. Implement `container_service.py` to make each test pass
4. Verify all unit tests pass before moving to Task 2

---

## TASK-2: reembed Integration (Phase 2)

### Description
Extend `reembed/cli.py` to use the container service helpers when running inside a
container. The existing native service management (`_is_service_running`, `_stop_service`,
`_restart_service`) continues to work for systemd/launchd — the container path is
selected via `is_in_container()`.

### Files to Modify
- `src/agentalloy/reembed/cli.py`

### Implementation Details

**Extend `_is_service_running()`**
- Add container check: if `is_in_container()`, call `_find_uvicorn_pid()` from container_service
- Otherwise, use existing systemd/launchd logic

**Extend `_stop_service()`**
- Add container check: if `is_in_container()`, call `stop_service_in_container()`
- Otherwise, use existing systemd/launchd logic

**Extend `_restart_service()`**
- Add container check: if `is_in_container()`, call `restart_service_in_container()`
- Otherwise, use existing systemd/launchd logic

**The `--no-restart` flag already suppresses `_restart_service()` — no changes needed
to the flag semantics.**

### Acceptance Criteria
- [ ] In container mode, reembed stops uvicorn via container_service before DB access
- [ ] In container mode, reembed restarts uvicorn via container_service after DB access
- [ ] `--no-restart` suppresses container restart (existing behavior extended)
- [ ] Native install (systemd/launchd) path is unchanged — container check is additive
- [ ] `finally` block in `main()` calls `_maybe_restart()` which respects container mode
- [ ] reembed CLI succeeds when service is running in a container

### TDD Instructions
1. Write tests in `tests/test_container_integration.py` (test cases RE-1 through RE-5)
2. Run tests — they should fail (container helpers not wired in)
3. Modify `reembed/cli.py` to import and use container_service when `is_in_container()`
4. Verify all integration tests pass

### Dependencies
- Task 1 must be complete (container_service.py must exist)

---

## TASK-3: install-packs Integration (Phase 3)

### Description
Add container-aware stop/restart wrapping to the `install-packs` subcommand. This
includes adding a `--no-restart` flag to the argparse parser and forwarding it through
to the reembed call chain.

### Files to Modify
- `src/agentalloy/install/subcommands/install_packs.py`
- `src/agentalloy/install/subcommands/reembed.py`

### Implementation Details

**install_packs.py: add `--no-restart` flag**
- Add `p.add_argument("--no-restart", action="store_true", ...)` to the `add_parser()` function
- Pass `no_restart=args.no_restart` to `_bulk_reembed()`
- Wrap `_bulk_reembed()` logic with container stop/restart:
  ```python
  def _bulk_reembed(no_restart: bool = False) -> int:
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

**reembed.py: forward `--no-restart` flag**
- Add `p.add_argument("--no-restart", action="store_true", ...)` to `add_parser()`
- Forward `--no-restart` in `_run()` via the `forwarded` list

### Acceptance Criteria
- [ ] `agentalloy install-packs --no-restart` suppresses both container and reembed restart
- [ ] install-packs wraps `_bulk_reembed()` with container stop/restart in try/finally
- [ ] `agentalloy reembed --no-restart` forwards the flag to reembed_main
- [ ] install-packs CLI succeeds when service is running in a container
- [ ] JSON output from install-packs is not contaminated by stderr messages

### TDD Instructions
1. Write tests in `tests/test_container_integration.py` (test cases IP-1 through IP-4)
2. Run tests — they should fail (no --no-restart flag, no container wrapping)
3. Add `--no-restart` flag to both install_packs.py and reembed.py subcommands
4. Wrap `_bulk_reembed()` with container stop/restart
5. Verify all integration tests pass

### Dependencies
- Task 1 must be complete

---

## TASK-4: ingest Integration (Phase 4)

### Description
Add container-aware stop/restart wrapping to the `ingest.py` CLI. Similar pattern to
reembed: stop service before DB access, restart after in a finally block.

### Files to Modify
- `src/agentalloy/ingest.py`

### Implementation Details

**Add `--no-restart` flag to argparse in `main()`**
- `parser.add_argument("--no-restart", action="store_true", ...)`

**Wrap `_single()` with container stop/restart**
```python
def _single(yaml_path, *, force, yes, strict, no_restart=False):
    container_stopped = False
    if is_in_container():
        container_stopped = stop_service_in_container()
    try:
        # existing ingest logic...
    finally:
        if container_stopped and not no_restart:
            restart_service_in_container()
```

**Wrap `_batch()` with container stop/restart**
- Same pattern as `_single()`, wrapping the DB open/close section

### Acceptance Criteria
- [ ] `ingest` stops uvicorn in container before opening LadybugDB
- [ ] `ingest` restarts uvicorn in container after DB access (even on error/exception)
- [ ] `--no-restart` flag suppresses container restart
- [ ] ingest CLI succeeds when service is running in a container
- [ ] Exit codes are preserved (EXIT_OK, EXIT_USAGE, EXIT_VALIDATION, EXIT_DB, EXIT_DUPLICATE)

### TDD Instructions
1. Write tests in `tests/test_container_integration.py` (test cases IG-1 through IG-3)
2. Run tests — they should fail
3. Add container stop/restart wrapping to `_single()` and `_batch()`
4. Add `--no-restart` flag to argparse
5. Verify all integration tests pass

### Dependencies
- Task 1 must be complete

---

## TASK-5: Unit Tests (Phase 5)

### Description
Comprehensive unit tests for the `container_service` module. These tests use mocking
to simulate container environments, process states, and Kuzu lock behavior.

### Files to Create
- `tests/test_container_service.py`

### Test Categories

**Container Detection (DC-1 to DC-5)**
- Patch `pathlib.Path.exists()` and `pathlib.Path.is_dir()` for `/.dockerenv` and `/app`
- Verify all combinations return correct boolean

**Process Detection (PD-1 to PD-5)**
- Create fake `/proc/<pid>/cmdline` files with uvicorn command lines
- Verify single PID, parent-child (lowest PID), no match, unreadable, non-matching commands

**Service Stop (SS-1 to SS-7)**
- Mock `os.kill` and `/proc/<pid>/status` to test SIGTERM success, SIGKILL escalation,
  no process found, permission errors, already-dead process

**Lock Verification (LV-1 to LV-4)**
- Mock `kuzu.Database` to test immediate release, retry success, timeout, non-lock errors

**Service Restart (SR-1 to SR-5)**
- Mock `subprocess.Popen` and `httpx.get` to test health OK, health timeout,
  spawn failure (FileNotFoundError), immediate exit, port in use

### Acceptance Criteria
- [ ] All 23 unit tests (DC-1..DC-5, PD-1..PD-5, SS-1..SS-7, LV-1..LV-4, SR-1..SR-5) pass
- [ ] Tests cover both direct podman run (PID 1) and compose entrypoint (child process)
- [ ] No real processes are spawned or killed during tests (full mock coverage)
- [ ] Tests use `tmp_path` and `monkeypatch` for clean isolation

### TDD Instructions
1. Write ALL test functions first, referencing the test plan document
2. Run tests — all should fail
3. Implement `container_service.py` to make each test pass
4. Run tests — all should pass
5. Do NOT proceed to Task 6 until all unit tests pass

---

## TASK-6: Integration Tests (Phase 6)

### Description
Integration tests that verify the full stop/restart flow for reembed, install-packs,
and ingest CLI commands when running in a container. These tests mock the container
environment and verify the correct call sequence.

### Files to Create
- `tests/test_container_integration.py`

### Test Categories

**reembed Integration (IE-1 through IE-4)**
- Full flow: detect -> stop -> verify lock -> reembed -> restart (exit 0, service back up)
- Service already stopped: detect -> no-op stop -> reembed -> no-op restart (exit 0)
- Lock still held: detect -> stop -> verify fails -> abort (exit non-0)
- Restart fails: detect -> stop -> reembed -> restart fails (exit 0, warning message)

**install-packs Integration (IP-1 through IP-4)**
- Full flow: detect -> stop -> install packs -> reembed -> restart (exit 0)
- `--no-restart` flag suppresses restart (restart not called)
- Reembed fails -> service still restarted (finally block)
- Service not running -> proceeds directly (no error)

**ingest Integration (IG-1 through IG-3)**
- Full flow: detect -> stop -> ingest -> restart (exit 0)
- `--no-restart` flag suppresses restart
- Service not running -> proceeds directly (no error)

### Acceptance Criteria
- [ ] All 11 integration tests pass
- [ ] Mocks verify correct call sequence (stop before, restart after)
- [ ] `finally` block behavior verified (restart on both success and exception)
- [ ] `--no-restart` verified to suppress restart in all three CLIs
- [ ] Native install path (is_in_container() = False) does NOT call container helpers

### TDD Instructions
1. Write all test functions first (IE-1..IE-4, IP-1..IP-4, IG-1..IG-3)
2. Run tests — they should fail (container helpers not wired into CLIs)
3. Implement integration code (Tasks 2, 3, 4)
4. Verify all integration tests pass

### Dependencies
- Tasks 1, 2, 3, 4 must be complete

---

## TASK-7: Edge Case Tests (Phase 7)

### Description
Tests for boundary conditions and error scenarios that are not covered by the happy-path
integration tests. These ensure robustness and graceful degradation.

### Files to Modify
- `tests/test_container_integration.py` (add edge case tests)

### Test Categories

**Service Not Running (EC-1, EC-2)**
- Container detected, no uvicorn process: stop returns False, operation proceeds
- Container detected, restart with no prior stop: restart called but service was never stopped

**Concurrent Execution (EC-3)**
- Verify stop_service_in_container() is idempotent (calling twice doesn't error)
- First command stops service, second finds no process (no-op stop)

**User Interrupt (EC-4)**
- Simulate KeyboardInterrupt during DB operation
- Verify service is still restarted in finally block

**Restart Failure (EC-5, EC-6)**
- Restart fails (port conflict): warning printed, operation exit code unchanged
- Restart fails (uvicorn crashes immediately): warning printed after 30s timeout

**Native Install Unchanged (EC-7, EC-8, EC-9)**
- Native systemd path is unchanged (is_in_container = False)
- Native launchd path is unchanged
- Not in container, no service manager: existing no-op behavior

### Acceptance Criteria
- [ ] All 9 edge case tests pass (EC-1 through EC-9)
- [ ] Stop is idempotent (no exception on second call)
- [ ] finally block always triggers restart even on KeyboardInterrupt
- [ ] Restart failure produces warning, does NOT change operation exit code
- [ ] Native install paths (systemd/launchd) are unaffected by container code

### TDD Instructions
1. Write all edge case test functions first
2. Run tests — they should fail on edge cases not yet handled
3. Add error handling for edge cases in container_service.py and CLI integrations
4. Verify all edge case tests pass

### Dependencies
- Tasks 2, 3, 4 must be complete (container helpers wired into CLIs)

---

## TASK-8: Regression Tests (Phase 8)

### Description
Verify that existing tests still pass after adding container-aware code. The container
logic is additive — it should not change behavior for native installs (systemd/launchd).

### Files to Run
- `tests/test_reembed.py` (existing tests)
- `tests/test_ingest.py` (existing tests, if present)
- `tests/test_storage_ladybug.py` (existing tests)
- `tests/install/test_verify.py` (existing tests)

### Regression Test Matrix (from test plan Section 6)
| Test | Source | Description |
|------|--------|-------------|
| R-1 | test_reembed.py:test_reembed_stops_and_restarts_service | Existing systemd stop/restart |
| R-2 | test_reembed.py:test_reembed_no_restart_flag | Existing --no-restart |
| R-3 | test_reembed.py:test_reembed_no_service_skip_stop | Existing no-service path |
| R-4 | test_reembed.py:test_reembed_restart_on_error | Existing error/restart path |
| R-5 | test_reembed.py:test_reembed_dry_run_stops_service | Existing dry-run path |
| R-6 | test_storage_ladybug.py | Existing LadybugStore tests |
| R-7 | test_ingest.py (if exists) | Existing ingest tests |
| R-8 | install/test_verify.py | Existing install verification tests |

### Acceptance Criteria
- [ ] All existing `tests/test_reembed.py` tests still pass
- [ ] All existing `tests/test_storage_ladybug.py` tests still pass
- [ ] All existing `tests/install/test_verify.py` tests still pass
- [ ] No new test failures introduced by container code
- [ ] Native install (systemd/launchd) behavior is identical to pre-change

### TDD Instructions
1. Run the full existing test suite BEFORE making any changes
2. Record baseline pass/fail counts
3. After implementing Tasks 1-7, run the full test suite again
4. Every test that passed before must still pass
5. Any regression = blocker — fix before merging

### Dependencies
- Tasks 1-7 must be complete

---

## Task Dependency Graph

```
Task 1 (container_service.py)
  |
  +---> Task 2 (reembed integration)
  |        |
  |        +---> Task 5 (unit tests) [parallel with Task 1]
  |        |
  |        +---> Task 6 (integration tests)
  |
  +---> Task 3 (install-packs integration)
  |        |
  |        +---> Task 6
  |
  +---> Task 4 (ingest integration)
           |
           +---> Task 6
                    |
                    +---> Task 7 (edge cases)
                    |
                    +---> Task 8 (regression)
```

## Parallelization Opportunities
- Task 1 (module) and Task 5 (unit tests) can be done in parallel — write tests first,
  then implement the module to satisfy them
- Task 2 (reembed), Task 3 (install-packs), and Task 4 (ingest) can be done in parallel
  once Task 1 is complete
- Task 6 (integration tests) should be done after Tasks 2, 3, 4 are complete
- Task 7 (edge cases) depends on Tasks 2, 3, 4
- Task 8 (regression) is last — verify everything still works
