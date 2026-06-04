# Design: Unified Setup UX with Direct Runtime Container Execution

## Overview

Refactor `agentalloy setup` container deployment from multi-service compose orchestration
to direct podman/docker runtime with a single all-in-one container. Unify the UX so both
native and container paths share the same discovery, review, and confirmation flow.

## Architecture

### Current State

```
run_setup()
  ├─ detect hardware
  ├─ preflight (early)
  ├─ prompt deployment (native / container)
  ├─ if container: _run_container_flow()  ← branches early, skips native prompts
  │     └─ compose-based: detect podman-compose, locate compose.yaml,
  │        run piecemeal stages (init → ollama → pack → main)
  ├─ if native: prompt runner/model/hardware/port/mode → packs → harness → upstream
  │     └─ pull_models → start_embed_server → install_packs → wire_harness → verify
  └─ review summary → confirm → done
```

### Target State

```
run_setup()
  ├─ detect hardware
  ├─ preflight (early)
  ├─ prompt deployment (native / container)
  ├─ (shared discovery)
  │     ├─ if native: prompt runner/model/hardware/port/mode/harness/upstream
  │     └─ if container: use fixed values (runner=ollama, port=47950, mode=manual, harness=manual)
  ├─ prompt packs (shared)
  ├─ review summary → confirm (y/n)
  ├─ if native: pull_models → start_embed_server → install_packs → wire_harness → verify
  ├─ if container: _run_container_flow()  ← now runs after shared discovery
  │     └─ direct runtime: detect podman/docker → build image → create volume → run container
  │        → wait for health → record state → verify
  └─ done
```

### Container Runtime Flow (new _run_container_flow)

```
1. Detect runtime binary (podman > docker, via shutil.which)
2. Locate build context:
   a. Check cwd for Containerfile + pyproject.toml + uv.lock
   b. Check parents[4] (editable install location)
   c. Auto-clone into ~/.cache/agentalloy/repo if not found locally
3. Preflight (container phase): runtime available, build assets present, port free
4. Build image: {runtime_binary} build -t agentalloy:local -f Containerfile <build_context>
5. Create volume: {runtime_binary} volume create agentalloy-data
6. Run container: {runtime_binary} run -d --replace --name agentalloy
     -p {port}:47950 -v agentalloy-data:/app/data
     -e AGENTALLOY_PACKS={packs} agentalloy:local
7. Wait for health: poll http://localhost:{port}/health (300s timeout, 2s backoff)
8. Record state to install_state
```

## File Changes

### src/agentalloy/install/subcommands/simple_setup.py

**SetupConfig dataclass** (lines ~60-95):
- REMOVE: `compose_binary: str`, `compose_file: str`
- ADD: `runtime_binary: str = ""`, `image_tag: str = "agentalloy:local"`,
       `container_name: str = "agentalloy"`, `data_volume: str = "agentalloy-data"`

**run_setup() orchestrator** (line ~1569):
- Move container branch to AFTER shared discovery (currently branches early at line ~1654)
- Add deployment choice prompt before shared discovery
- Add CPU-only warning for container with user confirmation
- Container path uses fixed values for native-only prompts (runner=ollama, port=47950, mode=manual, harness=manual)
- Native path unchanged

**_run_container_flow()** (line ~948, ~1256 lines):
- FULL REWRITE: Remove all compose-specific code
- New flow: detect runtime → locate build context → preflight → build → volume → run → health check → state
- Replace `_probe_compose_runtime()` with `shutil.which()` loop
- Replace compose service sequencing with direct podman/docker commands via `subprocess.run()`
- Replace one-shot container waits with health endpoint polling
- Add `_build_image()`, `_create_volume()`, `_run_container()`, `_wait_for_health()` helpers

**_probe_compose_runtime()**:
- REMOVE entirely (replaced by runtime detection in _run_container_flow)

### src/agentalloy/install/subcommands/preflight.py

**Container phase** (in `run_preflight()`):
- REPLACE: `_check_compose_binary()` → `_check_runtime_binary()`
- REMOVE: `_check_compose_file_present()`, `_check_image_build_deps()`
- ADD: `_check_build_context_present()` — search for Containerfile, pyproject.toml, uv.lock
- ADD: `_check_runtime_binary()` — verify podman or docker on PATH
- Keep: `_check_git_present()`, `_check_port_free()`

### src/agentalloy/install/state.py

**State migration** (in `load_state()`):
- Add migration logic: if `compose_binary` or `compose_file` keys exist, log warning and ignore them
- New keys: `runtime_binary`, `image_tag`, `container_name`, `data_volume`
- Existing keys preserved: `deployment`, `port`, `packs`, `harness`, `mode`, `runner`, `model`

### src/agentalloy/install/subcommands/wire.py

No changes expected — reads port from state, auto-detects harness. Works with both native and container.

### src/agentalloy/install/subcommands/doctor.py (if exists)

**Potential impact**: If doctor references `compose_binary`, update to use new state keys or
detect deployment mode. Check if file exists and update if needed.

### Containerfile (in agentalloy root)

**Update entrypoint**: Add in-container bootstrap script that handles:
1. Schema migrations (idempotent)
2. Start Ollama (background, 127.0.0.1:11434)
3. Wait for Ollama health
4. Pull embedding model (qwen3-embedding:0.6b)
5. Install packs if AGENTALLOY_PACKS env set
6. Start uvicorn (0.0.0.0:47950)
7. Trap SIGTERM for graceful shutdown

### compose.yaml (in agentalloy root)

No changes — remains in repo for advanced users but no longer part of setup path.

## API Changes

### New functions in simple_setup.py:

```python
def _detect_runtime_binary() -> str | None:
    """Return 'podman' or 'docker' from PATH, or None."""
    
def _locate_build_context() -> Path | None:
    """Search cwd → parents[4] → auto-clone for build context."""
    
def _build_image(runtime_binary: str, build_context: Path, image_tag: str = "agentalloy:local") -> int:
    """Run {runtime_binary} build -t <tag> -f Containerfile <context>."""
    
def _create_volume(runtime_binary: str, volume_name: str = "agentalloy-data") -> int:
    """Run {runtime_binary} volume create <name>."""
    
def _run_container(runtime_binary: str, port: int, packs: str,
                   container_name: str = "agentalloy",
                   data_volume: str = "agentalloy-data") -> int:
    """Run podman run -d with port mapping and volume mount."""
    
def _wait_for_health(port: int, timeout: int = 300, backoff: int = 2) -> bool:
    """Poll http://localhost:{port}/health until healthy or timeout."""
    
def _record_container_state(cfg: SetupConfig) -> None:
    """Save runtime_binary, image_tag, container_name, data_volume, port to install state."""
```

### New functions in preflight.py:

```python
def _check_runtime_binary() -> dict:
    """Check podman or docker is available on PATH."""
    
def _check_build_context_present(build_context: Path) -> dict:
    """Check Containerfile, pyproject.toml, uv.lock exist."""
```

### Removed functions in preflight.py:

```python
# REMOVE: _check_compose_binary()
# REMOVE: _check_compose_file_present(compose_file)
# REMOVE: _check_image_build_deps(compose_file)
```

## Data Changes

### SetupConfig fields (dataclass):

```python
@dataclass
class SetupConfig:
    # ... existing fields ...
    deployment: str = "native"
    # REMOVED: compose_binary: str = ""
    # REMOVED: compose_file: str = ""
    # NEW:
    runtime_binary: str = ""
    image_tag: str = "agentalloy:local"
    container_name: str = "agentalloy"
    data_volume: str = "agentalloy-data"
```

### Install state keys (JSON file):

```json
{
    "deployment": "container",
    "port": 47950,
    "runtime_binary": "podman",
    "image_tag": "agentalloy:local",
    "container_name": "agentalloy",
    "data_volume": "agentalloy-data",
    "packs": "",
    "harness": "manual",
    "mode": "manual",
    "runner": "ollama",
    "model": "qwen3-embedding:0.6b"
}
```

Old keys (`compose_binary`, `compose_file`) will be silently ignored during migration.

## Sequence

### Main use case: User runs `agentalloy setup` and chooses container

1. User runs `agentalloy setup` (interactive or non-interactive)
2. Hardware detection runs (GPU, RAM, disk)
3. Early preflight checks (port free, network, Python, uv, CLI, XDG dirs)
4. **Deployment choice prompt**: "Native install or container?"
   - Container shows CPU-only warning
   - User confirms or selects native
5. **Shared discovery** (packs prompt runs for both paths)
6. **Native-only prompts** (runner, model, hardware, port, mode, harness, upstream) — skipped for container
7. Review summary displayed
8. User confirms (y/n) or non-interactive proceeds
9. **Container execution**:
   a. Detect podman/docker binary
   b. Locate build context (cwd → parents[4] → auto-clone)
   c. Preflight (container phase): runtime, build assets, port
   d. Build image (`podman build`)
   e. Create volume (`podman volume create`)
   f. Run container (`podman run -d`)
   g. Wait for health endpoint (poll /health)
   h. Record state to install_state
   i. Run verify step
10. Done message

### Container bootstrap sequence (inside container):

1. Entry script runs on container start
2. Check if migrations already applied (idempotent)
3. Run migrations if needed
4. Start Ollama (background, 127.0.0.1:11434)
5. Poll Ollama /health until ready
6. Pull embedding model via Ollama API
7. If AGENTALLOY_PACKS env set, run install-packs
8. Start uvicorn on 0.0.0.0:47950
9. Trap SIGTERM for graceful shutdown

## Error Handling

### Runtime binary not found:
- Print clear error: "Neither podman nor docker found. Install one of them."
- Return exit code 1
- No state written

### Build context not found:
- Try auto-clone from GitHub
- If clone fails, print error with instructions
- Return exit code 1

### Build failure:
- Capture stderr from build command
- Print build output for debugging
- Return exit code 1

### Volume creation failure:
- Likely permission issue or existing volume conflict
- Print error with fix suggestion
- Return exit code 1

### Container run failure:
- Port already in use → suggest changing port
- Image not found → suggest rebuilding
- Permission denied → suggest checking podman/docker group
- Return exit code 1

### Health check timeout:
- Print error with troubleshooting steps:
  - "Container started but service not healthy after 300s"
  - "Check container logs: {runtime_binary} logs agentalloy"
  - "Common causes: Ollama failed to start, model pull failed, port conflict"
- Return exit code 1

### State recording failure:
- Exception caught, logged
- Container may still be running
- User can manually run `agentalloy doctor` to fix state

## Performance

### Build time:
- First build: ~1-2 minutes (pulls base image, installs deps)
- Subsequent builds: ~10-30 seconds (cached layers)

### Container startup:
- Ollama start: ~5-10 seconds
- Model pull: ~30-60 seconds (network dependent)
- Health check: 300s timeout with 2s backoff
- Total expected startup: ~60-120 seconds

### Optimizations:
- Build context detection cached in memory
- Health check uses exponential backoff (2s → 4s → 8s → ...)
- Volume creation is fast (<1s)
- Container run is immediate (returns container ID)

### Bottlenecks:
- Model pull is the longest step (network dependent)
- First build requires full image download
- Health polling blocks setup completion

## Security

### Container isolation:
- Container runs with default podman/docker security profile
- Port bound to 127.0.0.1 (not 0.0.0.0) — only localhost can reach API
- Volume mount is read-write for /app/data only
- No privileged mode, no host network, no PID namespace

### Build context:
- Auto-clone fetches from GitHub (verified URL)
- User can provide local build context to avoid network fetch
- No user input goes into build context path without validation

### Data persistence:
- /app/data on volume survives container restarts
- No sensitive data stored in image layers
- .env file not mounted into container (config via env vars only)

### GPU passthrough:
- Not supported in container (documented constraint)
- GPU users must choose native install
- No device flags in podman run command
