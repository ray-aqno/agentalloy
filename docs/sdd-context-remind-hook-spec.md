# Per-Turn Context Reminder Pattern

> **SUPERSEDED (2026-05-21).** The reminder pattern is sunset for both
> Skillsmith and Code-Indexer. Workflow-skill-driven injection (see
> `docs/signal-detection-and-domain-trigger-spec.md` and the build sequence
> under `docs/build-sequence/`) makes per-turn reminders redundant: the
> workflow skill is in the paid LLM's active context for the whole phase,
> and contract-driven retrieval handles domain skills without needing a
> separate language-level nudge.
>
> Kept here because the tier model (Tier 1 hooks, Tier 2 wrappers, Tier 3
> generated rules files), composition story, and per-harness binding
> mechanics still inform the architecture. The specific reminder script
> and `UserPromptSubmit` wiring described below are not part of the
> current design.

A shared pattern for tools that want to remind an agentic coding harness — at
the right moment, without being noisy — that the tool is available and how to
invoke it. Concrete providers conforming to this pattern:

- **Skillsmith provider** — `skillsmith/docs/skillsmith-remind-provider.md`
- **Code-Indexer provider** — `code-indexer-service/docs/code-indexer-remind-provider.md`

This document defines the contract, harness bindings, and composition story.
It does not describe any specific tool.

## Problem

Harnesses read their project-level instructions file (`CLAUDE.md`,
`.cursorrules`, `GEMINI.md`, etc.) once at session start. During long
sessions or across workflow-phase transitions, the model loses awareness of
the local tools available for grounding its work and falls back to writing
from scratch.

A reminder needs to: fire **per turn** where possible, **adapt** to the
current workflow phase if one is in use, **degrade gracefully** when the
tool isn't installed or reachable, and **compose** cleanly when multiple
tools ship their own reminders.

## Contract

Each tool ships its own executable script. The script is the portable
artifact. Bindings are harness-specific. Every conforming script MUST honor:

**Self-location**

- The script locates the project root by walking up from `$BASH_SOURCE`'s
  directory looking for a known marker (e.g. `.git`, or a tool-specific
  folder). Bindings do **not** need to set a particular working directory.

**Output discipline**

- **stdout**: zero or more reminder blocks. Each block is prefixed with a
  bracketed tool name on its own line (e.g. `[skillsmith]`, `[code-indexer]`).
  Empty when the tool decides not to fire.
- **stderr**: unused in normal operation.
- **exit code**: always `0`. A reminder script never blocks the user's
  prompt or the harness session.

**Behavioral guarantees**

- **Idempotent** and side-effect free. Safe to call any number of times per turn.
- **Bounded** — total execution <1s; each availability probe has a 1s timeout.
- **Local-only network** — no calls outside `127.0.0.1`.

**Gating is the provider's decision**

- Each tool decides for itself when to fire. Phase-aware gating (reading
  `.skillsmith/phase` or equivalent) is one strategy; presence-based gating
  (relevant files in repo) is another; always-on-when-installed is a third.
- A tool MUST NOT require a phase file to exist — if phase signals are
  unavailable, fall back to a sensible default rather than emitting nothing.

## Composition

Multiple conforming providers compose without an orchestrator:

- **Claude Code**: register each provider as its own entry in the
  `UserPromptSubmit` hooks array. They fire in registration order; each
  emits its own `[tool-name]` block.
- **Continue.dev**: register each provider as its own custom context
  provider. The model sees them as distinct context items.
- **Tier 3 (static rules)**: each provider gets its own marker pair in
  shared files (e.g. `SDD-CONTEXT-SKILLSMITH` and `SDD-CONTEXT-CODE-INDEXER`)
  so block-replacement updates one without touching the other.

A user who installs only one tool gets only that tool's reminder. A user
who installs both gets both, in install order, with no shared scaffolding.

## Bindings

Bindings fall into three tiers based on how dynamically the harness can
inject text. The examples below use `tools/<tool>-remind.sh` as a
placeholder — each provider doc will substitute its actual script path.

### Tier 1 — Native per-turn injection (full fidelity)

The script runs before every user prompt; stdout is appended to context for
that turn. Mid-session phase or availability changes take effect next prompt.

#### Claude Code (CLI)

`.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "bash tools/<tool>-remind.sh" }
        ]
      }
    ]
  }
}
```

Multiple tools: add additional `{ "type": "command", ... }` entries to the
inner `hooks` array. They fire in order.

#### Continue.dev (cloud or local LLM — same binding)

Custom context provider (`.continue/config.ts` or equivalent):

```ts
export const toolRemindProvider = {
  title: "<tool>-context",
  description: "<tool> reminder",
  type: "normal",
  getContextItems: async () => {
    const { stdout } = await execAsync("bash tools/<tool>-remind.sh");
    return stdout.trim()
      ? [{ name: "<tool>-context", description: "reminder", content: stdout }]
      : [];
  },
};
```

Local-LLM and cloud paths use the same provider; mechanism is independent
of model backend.

#### Hermes Agent / Claude Agent SDK / custom harnesses

Programmatic injection in the message-construction path:

```python
import subprocess

def reminder_prefix() -> str:
    return subprocess.run(
        ["bash", "tools/<tool>-remind.sh"],
        capture_output=True, text=True, timeout=2,
    ).stdout
```

Prepend to system message or merge into per-turn prefix.

### Tier 2 — Wrapper / external invocation

The harness has no per-turn hook but supports shell-out from chat or
accepts a read-only context file declared in its config.

#### OpenCode (sst/opencode)

OpenCode supports project-level instructions and a config file but does
not expose a per-turn pre-prompt shell hook in current releases. Use the
Tier 3 generated-rules pattern below, *or* — if a recent build adds agent
hooks or MCP-tool integration — register the script as a callable tool
the agent invokes on phase transitions. Verify current capability before
committing to a binding.

### Tier 3 — Static rules file (degraded, but workable)

The harness reads a rules file once per session. Per-turn dynamism is
lost, but **per-phase** dynamism can be preserved by regenerating the
rules file as part of whatever workflow step changes the tool's relevant
state (phase transition, service start/stop).

#### Generated-rules pattern (Cursor, Windsurf, Copilot, Cline, Gemini CLI, Aider)

Files that users hand-edit (Copilot instructions, `GEMINI.md`, `.clinerules`)
**must** use marker-delimited replacement to preserve authored content.
Files dedicated to the reminder can be overwritten directly.

```bash
# Replace (or append) a named block in a file, preserving the rest.
update_block() {
    local file="$1" marker="$2" body="$3"
    local begin="<!-- BEGIN $marker (auto-generated) -->"
    local end="<!-- END $marker -->"
    mkdir -p "$(dirname "$file")"
    touch "$file"
    if grep -qF "$begin" "$file"; then
        awk -v b="$begin" -v e="$end" -v body="$body" '
            $0==b {print; print body; skip=1; next}
            $0==e {skip=0; print; next}
            !skip {print}
        ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
    else
        { printf '\n%s\n%s\n%s\n' "$begin" "$body" "$end"; } >> "$file"
    fi
}

OUT=$(bash tools/<tool>-remind.sh)
MARKER="SDD-CONTEXT-<TOOL>"   # distinct per tool, enables composition

# --- dedicated files (safe to overwrite) ---

# Cursor — .mdc requires YAML frontmatter to register as a rule.
mkdir -p .cursor/rules
{
    printf -- '---\ndescription: <tool> reminder\nglobs: ["**/*"]\nalwaysApply: true\n---\n\n'
    printf '%s\n' "$OUT"
} > ".cursor/rules/<tool>-context.mdc"

# Windsurf — append to a shared file using markers (multiple tools may write here).
update_block .windsurfrules "$MARKER" "$OUT"

# Aider — declared once in .aider.conf.yml under `read:`.
mkdir -p .aider
printf '%s\n' "$OUT" > ".aider/<tool>-context.txt"

# --- shared files (always use marker-delimited replacement) ---

update_block .github/copilot-instructions.md "$MARKER" "$OUT"
update_block .clinerules                    "$MARKER" "$OUT"
update_block GEMINI.md                      "$MARKER" "$OUT"
```

Caveats:

- **Cursor / Windsurf** pick up rules edits on save without restart.
- **Aider** reads `read:` files at session start. Re-issue `/read .aider/<tool>-context.txt` after a phase change, or restart.
- **GitHub Copilot** re-reads `copilot-instructions.md` only on workspace reopen.
- **Cline** behaves like Copilot.
- **Gemini CLI** reads `GEMINI.md` at session start.

## Capability matrix

| Harness | Tier | Per-turn? | Mid-session phase change? |
|---|---|---|---|
| Claude Code (CLI) | 1 | ✅ | ✅ |
| Continue.dev (cloud) | 1 | ✅ | ✅ |
| Continue.dev (local LLM) | 1 | ✅ | ✅ |
| Hermes Agent | 1 | ✅ | ✅ |
| OpenCode | 2 or 3 | depends on installed version | depends |
| Aider | 3 | ❌ (`read:` file regenerated per phase) | ⚠️ in-session `/read` re-issue or restart |
| Cursor | 3 | ❌ (static file, auto-reload on save) | ✅ via rules regeneration |
| Windsurf | 3 | ❌ (static file, auto-reload on save) | ✅ via rules regeneration |
| GitHub Copilot (VS Code) | 3 | ❌ | ⚠️ requires workspace reload |
| Cline | 3 | ❌ | ⚠️ requires workspace reload |
| Gemini CLI | 3 | ❌ | ⚠️ requires new session |

## Design decisions

**Why one provider per tool, not one shared script?**
Tools must stand alone. A shared script implies a shared owner and forces
both tools to ship together. Per-tool providers conforming to a common
contract gives independent install/uninstall and clean composition.

**Why a contract instead of a library?**
Bash, ten harnesses, and tools written in different languages. The
lowest-friction interface is "script that prints to stdout and exits 0."
A library would constrain implementation language and add a dependency.

**Why allow Tier 3 if it's degraded?**
Half the supported harnesses only support Tier 3. A phase-regenerated
rules file is dramatically better than a generic always-on reminder.

**Why marker-delimited replacement for shared files?**
Multiple tools writing to `copilot-instructions.md` or `GEMINI.md` must
not stomp on each other or on the user's authored content. Distinct
markers per tool make the file safely co-editable.

## Reference: existing providers

| Tool | Provider doc |
|---|---|
| Skillsmith | `skillsmith/docs/skillsmith-remind-provider.md` |
| Code-Indexer | `code-indexer-service/docs/code-indexer-remind-provider.md` |
