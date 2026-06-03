# Unified Setup UX with Direct Runtime Container Execution

**Status:** Design Specification  
**Date:** 2026-06-03  
**Scope:** Refactor container deployment in `agentalloy setup` from multi-service compose orchestration to direct podman/docker runtime with embedded all-in-one container.

---

## 1. Problem Statement

The current setup wizard (`agentalloy setup`) has a bifurcated experience:

- **Native path**: Runs shared discovery prompts (runner, model, hardware, packs, harness), then executes sequential install steps.
- **Container path**: Branches early, skips native prompts, jumps straight to compose orchestration.

**Issues:**
1. Users see different UX based on deployment choice (inconsistent discovery/review).
2. Container path uses multi-service compose topology (agentalloy-init, ollama, ollama-pull, agentalloy-main services) requiring complex piecemeal sequencing.
3. Database lock ordering (migrations → embedder ready → ingest → API) is fragile across service boundaries.
4. Test maintenance burden: compose-specific assumptions scattered across test suite.
5. Container setup is heavier than needed: users want a single endpoint, not service choreography.

---

## 2. Objectives

1. **Unify UX**: Both native and container paths share the same discovery → review → execute flow.
2. **Simplify execution**: Replace compose with direct podman/docker commands; single container with internal orchestration.
3. **Single endpoint**: Host only needs to reach FastAPI on port 47950; all internal coordination (Ollama, Kuzu, DuckDB) happens inside the container.
4. **Preserve guarantees**: Database lock ordering and bootstrap idempotence remain intact.
5. **Reduce test complexity**: Direct runtime is easier to mock than compose service graphs.

---

## 3. Current Codebase Snapshot

### Key Files

**`src/agentalloy/install/subcommands/simple_setup.py`** (2100+ lines)
- `SetupConfig` dataclass (lines ~60–95): Holds all user config + resolved values.
  - **Current fields**: `runner`, `model`, `port`, `mode`, `packs`, `harness`, `preset`, `hardware_target`, `deployment`, `compose_binary`, `compose_file`, `upstream_*`, `detected_runner`, `recommended_host`, `models_output`.
  - **Compose-specific**: `compose_binary`, `compose_file`.
- `run_setup(cfg)` (line 1569): Main orchestrator.
  - **Current logic**: Detects hardware → prompts deployment → **branches early if container** (skips native prompts).
  - Line 1654: Container branch returns `_run_container_flow()` before packs/review.
- `_run_container_flow(cfg, t0)` (line 948, ~1256 lines): Compose-orchestrated container flow.
  - Detects compose binary → locates compose.yaml → runs piecemeal compose stages (init/ollama/pack/main).
  - Validates via compose-specific preflight checks.

**`src/agentalloy/install/subcommands/preflight.py`** (320+ lines)
- **Current container phase**: Checks for compose binary, compose file, image build deps.
- `_check_compose_binary()`, `_check_compose_file_present()`, `_check_image_build_deps()`.

**`tests/test_simple_setup.py`** (1700+ lines)
- `TestContainerFlow` class: Validates current compose behavior.
- Tests expect compose metadata in state, validate piecemeal stage ordering.

### Architecture Decision Points

1. **Database lock ordering** (documented in `docs/agentalloy/specs/container-kuzu-lock-resolution.md`):
   - Migrations (schema) must complete before embedder starts.
   - Embedder must be ready before ingest (install-packs) runs.
   - Ingest must complete before main API starts listening.
   - Current compose: orchestrates this via `depends_on` and one-shot services.

2. **Embedder location**: Currently a compose sidecar (`ollama` service). Moving to **internal to container**.

3. **Datastore location**: Both `ladybug` (Kuzu) and `skills.duck` (DuckDB) move **internal to container**.

---

## 4. Design Principles

1. **Shared discovery path**: Both native and container paths follow detect → prompt (deployment choice) → packs/review → execute (deployment-specific).
2. **Container self-contained**: No sidecar services. Single container image with embedded Ollama + Kuzu + DuckDB. All coordination happens inside via shell entrypoint.
3. **Direct runtime only**: Use `podman build`, `podman run`, `podman volume create`, etc. No compose binary dependency.
4. **Port binding**: Host ↔ container only on `127.0.0.1:{port} → 47950`. No internal orchestration visible to host.
5. **Idempotent bootstrap**: In-container startup script can be re-run without destructive side effects.
6. **CPU-only**: No GPU passthrough in container (GPU requires native install). Documented constraint.

---

## 5. Target Architecture

### UX Flow

```
setup start
  → detect hardware
  → preflight (early)
  → prompt: native or container?
  → (shared discovery)
      → prompt runner/model/hardware/port/mode [native only; container uses fixed values]
      → prompt packs [shared]
      → prompt harness [native only; container skips]
      → prompt upstream [native only; container skips]
  → review summary
  → confirm (y/n)
  → (deployment-specific execution)
      → if native: pull_models → start_embed_server → install_packs → wire_harness → verify
      → if container: build image → create volume → run container → wait for health → record state → verify
  → done
```

### Container Runtime Flow

1. **Preflight (early)**: Port free, network, Python, uv, CLI, XDG dirs.
2. **Detect runtime**: Locate podman or docker.
3. **Locate build context**: Search cwd → parents[4] → auto-clone from GitHub.
4. **Preflight (container)**: Runtime available, build assets present, port free.
5. **Build image**: `podman build -t agentalloy:local -f Containerfile <build_context>` (1-2 min).
6. **Create volume**: `podman volume create agentalloy-data` (persistent /app/data).
7. **Run container**: 
   ```
   podman run -d --replace --name agentalloy \
     -p {host_port}:47950 \
     -v agentalloy-data:/app/data \
     -e AGENTALLOY_PACKS={packs} \
     agentalloy:local
   ```
8. **Wait for health**: Poll `http://localhost:{port}/health` with 300s timeout, 2s backoff.
9. **Record state**: Save deployment, runtime_binary, image_tag, container_name, data_volume to install state.

### In-Container Bootstrap (Entrypoint)

The Containerfile entrypoint/CMD runs an initialization script that:

1. **Migrations**: `kuzu-cli` or Python ORM runs schema migrations on `/app/data/ladybug`.
2. **Start Ollama**: Background process, listen on `127.0.0.1:11434`.
3. **Wait for Ollama ready**: Poll `/health` with timeout.
4. **Pull embedding model**: `curl http://localhost:11434/api/pull -d '{"model": "qwen3-embedding:0.6b"}'`.
5. **Install packs** (if `AGENTALLOY_PACKS` env set): `agentalloy install-packs --packs <list>` (uses `RUNTIME_EMBED_BASE_URL=http://localhost:11434`).
6. **Start uvicorn**: `uvicorn agentalloy.main:app --host 0.0.0.0 --port 47950`.

---

## 6. Detailed Changes by File

### 6.1 `SetupConfig` Dataclass

**Remove:**
- `compose_binary: str`
- `compose_file: str`

**Add:**
- `runtime_binary: str = ""` — Full path to podman or docker binary.
- `image_tag: str = "agentalloy:local"` — Container image tag.
- `container_name: str = "agentalloy"` — Container instance name.
- `data_volume: str = "agentalloy-data"` — Persistent volume name.

**Unchanged:**
- `deployment`, `port`, `packs`, `harness`, `mode`, `runner`, `model`, `hardware_target`, `upstream_*`.

### 6.2 `run_setup()` Orchestrator

**Current behavior (lines ~1650–1670):**
```python
if cfg.deployment == "container":
    return _run_container_flow(cfg, t0)
# Native path continues...
```

**New behavior:**
1. Prompt deployment choice (native vs. container).
2. Show CPU-only warning for container; confirm with user.
3. **Run shared discovery** (packs):
   - If native: prompt runner, model, hardware, port, mode, harness, upstream.
   - If container: use fixed values (runner=ollama, model=qwen3-embedding:0.6b, port=47950, mode=manual, harness=manual).
4. Prompt packs (shared for both).
5. Show review summary.
6. Confirm (y/n).
7. **If native**: existing native flow (pull_models → start_embed_server → install_packs → wire → verify).
8. **If container**: call `_run_container_flow()`.

**Key:** Deployment branch now happens **after** shared discovery, not before.

### 6.3 `_run_container_flow()` — Full Rewrite

**Old logic** (compose-based):
- Detect podman-compose binary.
- Locate compose.yaml.
- Run compose up (piecemeal: init, ollama, pack, main).
- Wait for each one-shot service.

**New logic** (direct runtime):

1. **Preflight (early)**: Existing checks (port free, network, Python, uv).
2. **Detect runtime**:
   ```python
   runtime_binary = None
   for binary in ["podman", "docker"]:
       if shutil.which(binary) is not None:
           runtime_binary = binary
           break
   if runtime_binary is None:
       _print("[red]Neither podman nor docker found...")
       return 1
   cfg.runtime_binary = runtime_binary
   ```
3. **Locate build context**:
   - Check cwd for Containerfile + pyproject.toml + uv.lock.
   - Check parents[4] (editable install).
   - Auto-clone into `~/.cache/agentalloy/repo` if not found locally.
4. **Preflight (container)**: New checks (runtime available, build context present, port free).
5. **Build image**:
   ```bash
   podman build -t agentalloy:local -f Containerfile <build_context>
   ```
6. **Create volume**:
   ```bash
   podman volume create agentalloy-data
   ```
7. **Run container**:
   ```bash
   podman run -d --replace --name agentalloy \
     -p {cfg.port}:47950 \
     -v agentalloy-data:/app/data \
     -e AGENTALLOY_PACKS={cfg.packs} \
     agentalloy:local
   ```
8. **Wait for health**: Poll `http://localhost:{cfg.port}/health` (300s timeout, 2s backoff).
9. **Record state**:
   ```python
   st = install_state.load_state()
   st["deployment"] = "container"
   st["runtime_binary"] = cfg.runtime_binary
   st["image_tag"] = cfg.image_tag
   st["container_name"] = cfg.container_name
   st["data_volume"] = cfg.data_volume
   st["port"] = cfg.port
   install_state.save_state(st)
   ```

**Removed:** All compose-specific code (compose binary detection, service sequencing, one-shot container waits, etc.).

### 6.4 `preflight.py` — Container Phase

**Old checks:**
```python
elif phase == "container":
    checks.append(_check_compose_binary())
    checks.append(_check_git_present())
    checks.append(_check_compose_file_present(compose_file))
    checks.append(_check_port_free(port))
    checks.append(_check_image_build_deps(compose_file))
```

**New checks:**
```python
elif phase == "container":
    # Direct runtime checks
    checks.append(_check_runtime_binary())      # podman or docker available
    checks.append(_check_git_present())         # for auto-clone fallback
    checks.append(_check_build_context_present())  # Containerfile, pyproject.toml, uv.lock
    checks.append(_check_port_free(port))      # same as before
```

**New check implementations:**

- `_check_runtime_binary()`: Verify podman or docker on PATH.
- `_check_build_context_present()`: Search for build assets; warn if only fallback-clone is available.

**Removed:** `_check_compose_binary()`, `_check_compose_file_present()`, `_check_image_build_deps()` (old versions; new image build check is simpler).

### 6.5 `tests/test_simple_setup.py` — Test Updates

**Old assumptions:**
- Container flow skips native prompts → container flow branches before packs.
- State keys: `compose_binary`, `compose_file`.
- Piecemeal stage ordering (init → ollama → pack → main).

**New assumptions:**
- Container flow runs after shared discovery (like native path).
- State keys: `runtime_binary`, `image_tag`, `container_name`, `data_volume`.
- Direct runtime commands (build → create volume → run → health check).

**Test updates:**

1. `test_container_flow_skips_native_prompts` → **removed or renamed**. Container no longer skips shared discovery; it just uses fixed values for native-only prompts.

2. `test_container_flow_records_state`:
   ```python
   # Old
   assert st["compose_binary"] == "podman compose"
   assert st["compose_file"] is not None
   
   # New
   assert st["runtime_binary"] == "podman"
   assert st["image_tag"] == "agentalloy:local"
   assert st["container_name"] == "agentalloy"
   assert st["data_volume"] == "agentalloy-data"
   ```

3. `test_compose_binary_missing_exits_1` → `test_runtime_binary_missing_exits_1`:
   ```python
   # Mock shutil.which to return None
   assert "[red]Neither podman nor docker found" in output
   ```

4. Mock changes:
   - Instead of `patch("_probe_compose_runtime")`, use `patch("shutil.which")`.
   - Instead of mock compose service sequencing, mock subprocess.run for build/run/health commands.

---

## 7. Migration Strategy

### Phase 1: SetupConfig Fields
- Remove `compose_binary`, `compose_file`.
- Add `runtime_binary`, `image_tag`, `container_name`, `data_volume`.
- Update any code referencing old fields.

### Phase 2: Refactor run_setup() Flow
- Move container branch after shared discovery.
- Container path now uses fixed values for native-only prompts.
- Shared packs prompt before deployment-specific execution.

### Phase 3: Rewrite _run_container_flow()
- Replace all compose orchestration with direct runtime commands.
- Update preflight calls to pass runtime info instead of compose file.

### Phase 4: Update preflight.py
- Replace compose-specific checks with direct runtime checks.
- Simplify container phase validation.

### Phase 5: Update Tests
- TestContainerFlow: update mocks and assertions for direct runtime.
- TestPromptDeployment: verify container path now runs shared discovery.

### Phase 6: Validation
- Run full pytest suite.
- Manual dry-run on Linux and macOS (if feasible).

---

## 8. Test Impact

### Tests to Update

1. **test_simple_setup.py::TestContainerFlow** (~10 test methods):
   - Refactor mocks (shutil.which, subprocess.run instead of compose probing).
   - Update state assertions (new fields).
   - Remove assumptions about early branching.

2. **test_container_integration.py** (if exists):
   - Review for compose assumptions; update for direct runtime.

3. **test_container_edge_cases.py** (if exists):
   - Review for compose assumptions; update for direct runtime.

4. **Other tests**:
   - No changes expected to native path tests (still use existing orchestration).

### Test Coverage

- ✅ Runtime binary detection (podman available, docker fallback, neither found).
- ✅ Build context discovery (cwd, parents[4], auto-clone).
- ✅ Image build success.
- ✅ Volume creation.
- ✅ Container run success.
- ✅ Health check passes.
- ✅ State recorded correctly.
- ✅ Pack selection passed to container.
- ✅ Non-interactive mode works.

---

## 9. Backward Compatibility

### Breaking Changes

1. `compose_binary` and `compose_file` state keys no longer used.
   - **Mitigation**: State migration code can be added to detect old keys and ignore them.

2. `agentalloy doctor` and other tools that reference `compose_binary`:
   - **Mitigation**: Update these tools to use new runtime state keys or detect deployment mode.

3. Manual `compose.yaml` workflows:
   - **Note**: `compose.yaml` remains in the repo for advanced users who want multi-service orchestration; it's just not part of the default setup path.

### Preserving Behavior

- ✅ Database lock ordering is preserved (in-container entrypoint enforces it).
- ✅ Embedder + datastore internals remain the same (just moved inside container).
- ✅ Port binding behavior unchanged (47950 internal → host port).
- ✅ Packs and skill discovery unchanged.
- ✅ Native install path completely unchanged.

---

## 10. Known Constraints & Limitations

1. **Container is CPU-only**: GPU users must choose native install. Documented in setup prompt.
2. **Bootstrap idempotence**: In-container init script must handle re-runs (e.g., if container is restarted).
3. **Single container instance**: Running multiple agentalloy containers requires manual naming (--container-name). Setup assumes single default instance per host.
4. **No volume permissions customization**: Data volume mounted at /app/data inside container; host uid/gid mapping not configurable in setup.

---

## 11. Risks & Mitigations

| Risk | Likelihood | Severity | Mitigation |
|------|-----------|----------|-----------|
| In-container Ollama fails to start | Medium | High | Health check timeout surfaces this; user sees clear "service did not become healthy" message. |
| Database lock contention on restart | Low | Medium | Idempotent entrypoint script; re-runs are safe. |
| Test suite regression on compose removal | Medium | Medium | Comprehensive test updates + validation on all platforms. |
| Users expect compose.yaml to be part of setup | Low | Low | Documentation + comment in compose.yaml explaining it's optional/advanced. |
| Build context auto-clone failure | Low | High | Fallback to interactive prompt; detailed error message. |

---

## 12. Acceptance Criteria

✅ **UX Unified**: Native and container paths share discovery → review → execute flow.  
✅ **Container simplified**: Single `podman run` replaces compose orchestration.  
✅ **Database lock preserved**: In-container bootstrap enforces migration → embedder → ingest → API sequencing.  
✅ **State recorded**: New runtime fields (runtime_binary, image_tag, etc.) saved to install state.  
✅ **Tests updated**: TestContainerFlow passes with new mocks; no native path regressions.  
✅ **Preflight simplified**: Container phase checks runtime/build context instead of compose.  
✅ **Docs updated**: Comments in code explain lock ordering and in-container bootstrap.

---

## 13. Further Considerations

1. **In-container entrypoint script**: Needs to be written / added to Containerfile. Should be:
   - Idempotent (safe to re-run).
   - Verbose logging to help debug bootstrap failures.
   - Handle graceful shutdown (trap SIGTERM).

2. **Tool compatibility**: Verify `agentalloy doctor`, `agentalloy verify`, and other tools work with new state keys.

3. **Documentation**: Update install guide, troubleshooting, and architecture docs to reflect direct runtime + single container.

4. **Future: GPU support**: If GPU support is added to container, it would require multi-stage builds or runtime-specific images. Current design does not prevent this; just marks it as out-of-scope for MVP.

5. **Release notes**: Highlight the UX unification and compose removal from the default setup path (compose.yaml still available for advanced use).

---

## References

- **Current lock-ordering spec**: `docs/agentalloy/specs/container-kuzu-lock-resolution.md`
- **Compose template**: `compose.yaml` (remains in repo; not part of setup path)
- **Containerfile**: `Containerfile` (updated to include entrypoint script for bootstrap)
- **Install state schema**: `src/agentalloy/install/state.py`
