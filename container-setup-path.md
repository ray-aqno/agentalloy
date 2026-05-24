# Spec: Container Deployment Path in Setup Wizard

## Background

`compose.yaml` already ships a complete multi-service stack (agentalloy + ollama + ollama-pull init service). `Containerfile` is production-ready. The `agentalloy setup` wizard has no awareness of either — users who want container deployment must discover and run compose manually.

This spec adds container deployment as a first-class, wizard-guided path.

---

## Goal

When a user runs `agentalloy setup`, they are asked upfront whether they want a **native** install or a **container** install. Choosing container short-circuits the native wizard steps (runner, model, hardware, service mode) and instead: validates prerequisites and runs `podman compose up -d` (or `docker compose up -d`). The wizard exits with the service running and verified. Port is always 47950 in container mode — fixed by compose.

---

## What Already Exists (no changes needed)

- `compose.yaml` — three-service stack: `ollama`, `ollama-pull` (init), `agentalloy`. Env vars (`RUNTIME_EMBED_BASE_URL`, `RUNTIME_EMBEDDING_MODEL`, etc.) are defined inline. No `.env` file required.
- `compose.radeon.yaml` — AMD variant; same pattern.
- `Containerfile` — builds the agentalloy image. No changes needed.

---

## Changes Required

### 1. `simple_setup.py` — new deployment prompt and container branch

**New question added as step 1** (before runner/model/hardware):

```
Select deployment type:
  1. Native  — runs directly on this host (systemd or manual)
  2. Container — managed by podman/docker compose (recommended for new installs)
```

Default: **Container** (index 2).

If **Native** is chosen → existing flow, unchanged.

If **Container** is chosen:

1. **Skip** runner, model, hardware, service-mode prompts entirely.
2. **Detect compose binary**: prefer `podman compose`, fall back to `docker compose`. If neither found, print remediation and exit 1.
3. **Detect GPU variant**: reuse `_detect_hardware()` already in `simple_setup.py`. If `radeon` → use `compose.radeon.yaml`; all others → `compose.yaml`.
4. **Port**: always 47950. No prompt. Users who need a different port must edit `compose.yaml` directly (a comment in the file explains this). Display port as read-only in the summary.
5. **Show summary** (same confirmation gate as native):
   - Deployment: container
   - Compose file: `compose.yaml` (or `compose.radeon.yaml`)
   - Compose binary: `podman compose` (or `docker compose`)
   - Port: 47950
6. **Execute**:
   a. Run `podman compose -f <compose_file> up -d --build` (blocking, streaming output).
   b. Poll `http://localhost:<port>/health` up to 120 s, 5 s interval.
   c. Run `agentalloy verify` (existing subcommand).
7. **Record state**: set `deployment: "container"` and `compose_file: "<path>"` in install state.
8. **Wire harness**: offer harness selection and run `wire-harness` exactly as native path does — the harness just needs the port, it doesn't care about deployment type.

**New `SetupConfig` fields**:

```python
deployment: str = ""          # "native" | "container"
compose_binary: str = ""      # "podman compose" | "docker compose"
compose_file: str = ""        # abs path to compose yaml used
```

### 2. `state.py` — new state fields

Add to `_empty_state()`:

```python
"deployment": None,          # "native" | "container" | None (pre-setup)
"compose_file": None,        # path used, container installs only
"compose_binary": None,      # binary used, container installs only
```

Add to `_migrate()` for schema v2 → v3: `data.setdefault("deployment", None)` etc.
Bump `CURRENT_SCHEMA_VERSION` to 3.

### 3. `preflight.py` — new container preflight phase

Add a third phase: `"container"`.

Checks:

| Check name | Pass condition |
|---|---|
| `compose_binary` | `podman compose version` or `docker compose version` exits 0 |
| `compose_file_present` | target `compose.yaml` exists at repo root |
| `port_free` | port 47950 (or configured port) is not bound |
| `image_build_deps` | `Containerfile` present (trivial — same dir as compose) |

This phase is called **instead of** the runner phase for container deployments. The existing `early` phase still runs first (Python version, uv, XDG dirs, network, port free).

### 4. `add_parser` in `simple_setup.py`

New CLI flag:

```
--deployment {native,container}
```

Non-interactive (`-n`) default: `native` (preserves existing CI behavior).

---

## Open Questions

1. ~~**Port override in container mode**~~ — **Resolved**: container mode locks to 47950. No port prompt. Users needing a different host port edit `compose.yaml` directly; add a comment there pointing to the `ports:` mapping.

2. ~~**Radeon compose variant**~~ — **Resolved**: auto-detect via `_detect_hardware()`, then prompt to confirm before proceeding:
   > `Detected compose file: compose.radeon.yaml — correct? [Y/n]`
   If the user answers no, prompt for a path. This covers mis-detection without adding a CLI flag.
   Add to the wizard flow between steps 3 and 4 (after detection, before summary).

3. **Image source**: `compose.yaml` currently does a local build (`build: context: .`). For first-time users without the source, this is fine (they cloned the repo). For a future PyPI-only install path, we'd need a pre-built image on a registry. Out of scope here.

4. ~~**Uninstall**~~ — **Resolved**: `uninstall.py` gains a container branch that reads `deployment` from install state. If `"container"`, runs `podman/docker compose -f <compose_file> down -v` (using the stored `compose_binary` and `compose_file`). Stops containers and removes volumes. Add to the `Files to Create / Modify` table.

---

## Files to Create / Modify

| File | Change |
|---|---|
| `src/agentalloy/install/subcommands/simple_setup.py` | New deployment prompt, container branch, `SetupConfig` fields |
| `src/agentalloy/install/state.py` | `deployment`, `compose_file`, `compose_binary` fields; schema v3 migration |
| `src/agentalloy/install/subcommands/preflight.py` | New `container` phase with 4 checks |
| `src/agentalloy/install/subcommands/uninstall.py` | Container branch: `compose down -v` using stored binary + file from state |
| `tests/install/test_simple_setup.py` | Unit tests for container branch; mock compose invocation |
| `tests/install/test_preflight.py` | Tests for container phase checks |
| `tests/install/test_uninstall.py` | Tests for container uninstall branch |

No changes to `Containerfile`, `compose.yaml`, or `compose.radeon.yaml`.

---

## Non-Goals

- Bundling Ollama into the Containerfile (it's already in compose as a separate service).
- Support for `lm-studio` or `llama-server` in container mode (Ollama only via compose; others can be added later).
- Auto-pushing images to a registry.
- Windows support (Podman Desktop / Docker Desktop are fine; the CLI commands are identical).
