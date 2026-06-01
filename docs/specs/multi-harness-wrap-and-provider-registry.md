# Multi-Harness Wrap & Provider Registry

## Problem Statement

AgentAlloy already intercepts agent LLM traffic the same way Headroom does — a
local HTTP proxy speaking `/v1/messages` (Anthropic) and `/v1/chat/completions`
(OpenAI), with per-harness installers that flip the agent's base URL at the
provider boundary. The interception model works. The integration surface does
not scale:

1. **Wiring is per-harness ad-hoc code.** All proxy-wiring logic lives in
   `src/agentalloy/install/subcommands/wire_harness.py` (~1700 lines). Each
   harness has its own `_wire_proxy_<name>` function with hardcoded paths,
   sentinel formats, env-var names, and uninstall semantics. Adding a harness
   means editing the monolith and re-running all of its tests.

2. **No `wrap` UX.** The Headroom equivalent is `headroom wrap claude` —
   start the proxy, spawn the agent as a child process with the right env vars
   set inline, tear everything down on exit. AgentAlloy requires the user to
   either run `agentalloy install` (writes a persistent env file they must
   `source` manually, e.g. `source ~/.agentalloy/claude-code-env.sh`) or
   accept markdown-injection wiring. The result is friction at first run and
   silent staleness (env file diverges from the running proxy port).

3. **Coverage gaps vs. the field.** AgentAlloy does not wire OpenAI Codex CLI,
   GitHub Copilot CLI, OpenClaw, or framework SDKs (LangChain, LiteLLM,
   Strands, Agno) despite all of them being interceptable through the existing
   proxy. Headroom ships installers for each in ~30 lines apiece because the
   proxy half is shared; AgentAlloy can do the same.

4. **No clear separation between "interceptable" and "instruction-only"
   harnesses.** `PROXY_UNABLE_HARNESSES` (`install/__init__.py:14`) lists four
   harnesses that can't accept a base-URL override (cursor, windsurf,
   github-copilot, gemini-cli). The rest mix markdown-injection wiring and
   real proxy wiring under the same CLI surface, which obscures what the
   user is actually getting.

## Goals

- A `agentalloy wrap <harness> [-- <args>]` command that:
  - Starts the proxy if not already running on the configured port.
  - Spawns the named harness as a child process with the correct base-URL
    env vars set in its environment (no manual `source`).
  - Streams the child's stdout/stderr through, propagates exit code,
    tears down the proxy on exit if it was started by `wrap`.
- A `providers/<harness>/` package layout (mirroring Headroom's
  `headroom/providers/<harness>/`) where each harness owns ~3 small files:
  `runtime.py` (env builder), `install.py` (persistent config writer), and
  `__init__.py` (re-exports). The wire_harness.py monolith shrinks to a
  dispatcher over a registry.
- A central `HarnessSpec` dataclass making every harness declare: which env
  vars it honors, which config file it reads (if any), which wire protocol
  the proxy must speak to it (Anthropic vs OpenAI), and whether it can be
  intercepted at all (capability: `proxy` | `markdown_only` | `mcp_only`).
- Initial wave of new harnesses behind the registry: **codex** (OpenAI
  Codex CLI), **copilot-cli** (GitHub Copilot CLI), **openclaw**.
- A `agentalloy install --harness <name>` path that uses the same registry
  to produce persistent config (the current behavior), so `wrap` and
  `install` share their per-harness knowledge.

## Non-Goals

- Replacing markdown-injection wiring for `PROXY_UNABLE_HARNESSES`
  (cursor, windsurf, github-copilot IDE, gemini-cli). Those stay on the
  injection path; the registry just labels them.
- Framework-SDK callbacks (LangChain / LiteLLM / Agno / Strands shims).
  Headroom has these under `integrations/`; deferring them to a follow-up
  spec so this one stays scoped to subprocess-launched harnesses.
- Changing the proxy itself. The proxy already speaks both wire protocols
  (`proxy_router.py`, `proxy_anthropic_router.py`); this spec only changes
  how harnesses are pointed at it.
- Reworking the install state machine (`install/state.py`) or the
  sentinel/uninstall scheme. Each provider module continues to emit the
  same `{path, action, content_sha256, original_content}` records.

## Design

### Provider package layout

```
src/agentalloy/providers/
  __init__.py              # registry: name → HarnessSpec
  base.py                  # HarnessSpec, Capability enum, shared helpers
  claude_code/
    __init__.py
    runtime.py             # build_launch_env(port) -> dict[str,str]
    install.py             # apply_persistent_config(port) -> list[FileRecord]
  codex/
    runtime.py, install.py
  copilot_cli/
    runtime.py, install.py
  openclaw/
    runtime.py, install.py
  aider/
    runtime.py, install.py
  opencode/
    runtime.py, install.py
  cline/
    runtime.py, install.py
  continue_dev/
    runtime.py, install.py
  hermes_agent/
    runtime.py, install.py
```

`HarnessSpec` (in `providers/base.py`):

```python
@dataclass(frozen=True)
class HarnessSpec:
    name: str                          # CLI identifier, e.g. "claude-code"
    binary: str | None                 # subprocess to spawn, e.g. "claude"; None = SDK-only
    capability: Capability             # PROXY | MARKDOWN_ONLY | MCP_ONLY
    protocol: Protocol                 # ANTHROPIC | OPENAI | EITHER
    env_builder: Callable[[int], dict[str, str]]   # for `wrap`
    install_writer: Callable[[int, Path], list[FileRecord]] | None  # for `install`
    install_reverter: Callable[[FileRecord], None] | None
```

`__init__.py` collects these into a `REGISTRY: dict[str, HarnessSpec]`.

Migration: each existing `_wire_proxy_<name>` function in
`wire_harness.py` moves verbatim into the matching
`providers/<name>/install.py` as `apply_persistent_config`. The
dispatcher in `_wire_proxy` becomes a one-liner registry lookup. No
behavior change for `install`; the move is purely structural.

### `wrap` command

New module: `src/agentalloy/install/subcommands/wrap.py`.

```
agentalloy wrap <harness> [--port N] [--no-start-proxy] [-- <args passed to harness>]
```

Flow (mirrors `headroom/cli/wrap.py` but reuses agentalloy's existing
proxy lifecycle):

1. Resolve `HarnessSpec` from registry; fail fast on unknown name or
   `capability != PROXY`.
2. Resolve port from CLI flag → `AGENTALLOY_PROXY_PORT` env → config →
   default `47950`.
3. Probe `127.0.0.1:<port>` with a 1s TCP connect (same idiom as
   `headroom/cli/wrap.py:_check_proxy`).
4. If not running and `--no-start-proxy` is unset:
   spawn the proxy via the existing `install/server_proc.py` machinery
   in background; poll for readiness; record PID for teardown.
5. Build child env: `os.environ.copy() | spec.env_builder(port)`.
   Example for claude-code:
   `{ANTHROPIC_BASE_URL: "http://127.0.0.1:47950", ANTHROPIC_API_KEY: "agentalloy"}`.
6. Resolve `spec.binary` via `shutil.which`; error clearly if missing.
7. `subprocess.run([binary, *user_args], env=child_env)` with stdio
   inherited.
8. On child exit (or SIGINT in parent): if we started the proxy, stop it.
   Propagate the child's exit code as our own.

Idempotent re-runs: probing the port before spawning means
`agentalloy wrap claude-code` in two terminals shares one proxy.

### Initial new providers

Each is a ~30-line `runtime.py` + ~30-line `install.py` based on the
Headroom equivalents under `~/tools/headroom/headroom/providers/`:

- **codex** — `OPENAI_BASE_URL=http://127.0.0.1:<port>` env-var hijack
  for the CLI; for persistent install, the TOML block in
  `~/.codex/config.toml` (see headroom `providers/codex/install.py` for
  the marker pattern). Binary: `codex`.
- **copilot-cli** — env-var: `GITHUB_COPILOT_API_URL` (or whichever the
  CLI honors; pin via the headroom impl). Binary: `gh-copilot` or
  `copilot` depending on install path.
- **openclaw** — JSON-block injection into the OpenClaw plugin config
  (`~/.openclaw/plugins.json`), same sentinel scheme as cline.
  Binary: `openclaw` if a launchable mode exists; otherwise
  install-only.

### Existing harnesses: relabel, don't rewrite

Annotate the registry so `PROXY_UNABLE_HARNESSES` becomes a derived
view (`spec.capability == MARKDOWN_ONLY`). The four current entries
(cursor, windsurf, github-copilot, gemini-cli) keep their existing
markdown-injection writers but expose `env_builder = None`, so
`wrap` rejects them with a clear "this harness can't be proxied; use
`agentalloy install --harness <name>` instead" message.

### CLI surface changes

- New: `agentalloy wrap <harness>` (this spec).
- Unchanged: `agentalloy install --harness <name>` keeps writing
  persistent config via the same per-provider `install.py` modules.
- Unchanged: the `wire-harness` internal subcommand keeps working
  during the migration; eventually deprecated in a follow-up.

## Migration Plan

1. **Add `providers/` skeleton.** Land `providers/base.py` (HarnessSpec,
   enums) and an empty `REGISTRY`. No call sites yet.
2. **Move one provider end-to-end as proof.** Pick `claude-code` because
   it has the simplest existing wirer. Move
   `_wire_proxy_claude_code` from `wire_harness.py` to
   `providers/claude_code/install.py`. Add `runtime.py` with the env
   builder. Register in `REGISTRY`. Have `_wire_proxy` dispatch via the
   registry for this one harness. Existing tests must pass unchanged.
3. **Implement `wrap` against the one migrated provider.** Land
   `wrap.py` and a smoke test that runs
   `agentalloy wrap claude-code -- --version` against a fake `claude`
   binary on PATH. Verify env vars in the child process.
4. **Migrate remaining existing harnesses.** Per-PR, move
   aider/opencode/cline/continue/hermes/cursor/windsurf/github-copilot/
   gemini-cli/manual to their own `providers/<name>/` packages. Each
   PR is mechanical and self-contained.
5. **Add new harnesses.** codex, copilot-cli, openclaw — each as its
   own PR off the now-stable registry. Each adds one test that
   verifies `build_launch_env` returns the right keys.
6. **Deprecate the inline dispatch in `wire_harness.py`.** Once every
   harness lives under `providers/`, the file collapses to thin
   argparse glue over the registry.

## Testing

- **Unit:** for each provider, assert `env_builder(port)` returns the
  expected env-var keys/values. For `install.py`, snapshot the file
  written for `port=47950` and verify the sentinel block round-trips
  through the existing uninstall machinery.
- **Integration:** create a fake `claude` shim on PATH that prints
  `os.environ.get("ANTHROPIC_BASE_URL")` and exits. Run
  `agentalloy wrap claude-code` (with proxy mocked / started in
  test fixture); assert the shim saw
  `http://127.0.0.1:<port>`. Repeat for each PROXY-capable harness.
- **Lifecycle:** test that `wrap` started in foreground, killed with
  SIGINT, leaves no orphan proxy when it started the proxy itself,
  and leaves a pre-existing proxy alone when it did not.
- **Backwards compat:** existing `wire-harness` integration tests
  (`tests/install/test_wire_harness*.py`) must pass unchanged
  through the migration; they exercise the install path which is
  delegated to the same provider modules.

## Open Questions

- Should `wrap` write a transient PID file under `~/.agentalloy/run/`
  so a second `wrap` invocation can attach to a running proxy without
  re-probing? (Headroom does; the port probe is fine for v1.)
- For `PROXY_UNABLE_HARNESSES`, do we still want them in the
  registry at all, or split them into a separate
  `injectors/` package to make the capability boundary obvious in
  the code layout? (Recommend keeping them in `providers/` with a
  `capability=MARKDOWN_ONLY` label — one place to look.)
- Framework-SDK shims (LangChain / LiteLLM / Agno / Strands) — defer
  to a follow-up spec, or fold a minimal LiteLLM callback into this
  one to cover the "library, not subprocess" case?
