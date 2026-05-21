# Phase 5: Tier 3 Hardening

**Prerequisites:** Phase 3 complete (the signal layer works on Tier 1 / Claude Code). Phase 4 helpful but not required.

**Goal:** Bring usable Skillsmith behavior to Tier 3 harnesses (Cursor,
Windsurf, GitHub Copilot, Cline, Gemini CLI, Aider) that don't support
per-turn hooks. Use a file-watching sidecar to regenerate harness-specific
rules files on phase transitions and contract writes. Be **loudly explicit**
that Tier 3 is a reduced experience.

**Done means:** all acceptance criteria pass, the sidecar runs reliably,
the README clearly marks Tier 3 caveats, and setup-time messaging warns
users selecting Tier 3 harnesses.

## Files to create

| Path | Purpose |
|---|---|
| `src/skillsmith/watch/__init__.py` | Package init |
| `src/skillsmith/watch/watcher.py` | File-system watcher loop |
| `src/skillsmith/watch/regenerators.py` | Per-harness rules-file generators (marker-block aware) |
| `src/skillsmith/install/subcommands/watch.py` | `skillsmith watch {start, stop, status}` |
| `docs/tier3-experience.md` | User-facing doc about Tier 3 limitations + workarounds |
| `tests/test_watch.py` | Watcher loop + regenerator tests |

## Files to modify

| Path | What changes |
|---|---|
| `README.md` | Add a "Harness support tiers" section explicitly listing what each tier gets |
| `src/skillsmith/install/subcommands/simple_setup.py` | When user picks a Tier 3 harness, print a clearly-marked block listing reduced functionality + offer to enable the sidecar |
| `src/skillsmith/install/subcommands/wire_harness.py` | For Tier 3 harnesses, write a `~/.skillsmith/watch/<profile>.yaml` config and prompt the user to start the sidecar |

## Step-by-step

### Step 5.1 — File-system watcher

**Create** `src/skillsmith/watch/watcher.py`.

Use `watchdog` (mature, cross-platform) for file events. Add to deps if not present.

```python
@dataclass
class WatchConfig:
    project_root: Path
    profile_name: str
    harness: str                # "cursor" | "windsurf" | "copilot" | "cline" | "gemini" | "aider"
    poll_interval_s: float = 1.0
    debounce_ms: int = 500

def run_watcher(config: WatchConfig) -> None:
    """Long-running loop. Watches:
       - .skillsmith/phase  → regenerate on change
       - .skillsmith/contracts/**  → regenerate when new contract written
    """
```

On phase-file change:

1. Read new phase.
2. Load workflow skill for new phase from active profile's datastore.
3. Call regenerator for the configured harness with the workflow skill's prose.

On contract write:

1. Parse contract.
2. Call `skillsmith compose --contract <path>` → get composed text.
3. Call regenerator with the composed text + (if reachable) code-indexer output.

Debounce: if multiple file events arrive within `debounce_ms`, coalesce.

**Acceptance criteria:**

- [ ] Watcher starts, runs, stops cleanly on SIGTERM.
- [ ] Survives transient errors (e.g., partial file writes) without dying.
- [ ] Logs to `~/.skillsmith/watch/<profile>.log` for diagnostics.
- [ ] Idempotent regeneration: same input → same rules file content (byte-equal).

### Step 5.2 — Per-harness regenerators

**Create** `src/skillsmith/watch/regenerators.py`.

```python
# Marker pair used by every regenerator. Per-tool markers enable composition
# with other tools (e.g., code-indexer also writes blocks with its own marker).
SKILLSMITH_MARKER = "SKILLSMITH-CONTEXT"

def regenerate_cursor(content: str, project_root: Path) -> None:
    """Write to .cursor/rules/skillsmith-context.mdc with YAML frontmatter."""
    path = project_root / ".cursor" / "rules" / "skillsmith-context.mdc"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = f"""---
description: Skillsmith phase + contract context
globs: ["**/*"]
alwaysApply: true
---

{content}
"""
    path.write_text(body)

def regenerate_windsurf(content: str, project_root: Path) -> None:
    """Marker-block replacement in .windsurfrules."""
    update_block(project_root / ".windsurfrules", SKILLSMITH_MARKER, content)

def regenerate_copilot(content: str, project_root: Path) -> None:
    """Marker-block replacement in .github/copilot-instructions.md."""
    update_block(project_root / ".github" / "copilot-instructions.md", SKILLSMITH_MARKER, content)

def regenerate_cline(content: str, project_root: Path) -> None:
    """Marker-block replacement in .clinerules."""
    update_block(project_root / ".clinerules", SKILLSMITH_MARKER, content)

def regenerate_gemini(content: str, project_root: Path) -> None:
    """Marker-block replacement in GEMINI.md."""
    update_block(project_root / "GEMINI.md", SKILLSMITH_MARKER, content)

def regenerate_aider(content: str, project_root: Path) -> None:
    """Write to .aider/skillsmith-context.txt (declared in .aider.conf.yml read:)."""
    path = project_root / ".aider" / "skillsmith-context.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

REGENERATORS: dict[str, Callable] = {
    "cursor": regenerate_cursor,
    "windsurf": regenerate_windsurf,
    "copilot": regenerate_copilot,
    "cline": regenerate_cline,
    "gemini": regenerate_gemini,
    "aider": regenerate_aider,
}

def update_block(path: Path, marker: str, body: str) -> None:
    """Replace (or append) a named SKILLSMITH-CONTEXT block in `path`,
    preserving the rest of the file. Same algorithm as the (superseded)
    reminder pattern's update_block helper."""
```

**Acceptance criteria:**

- [ ] All six regenerators implemented.
- [ ] `update_block` preserves all non-block content byte-for-byte.
- [ ] First call appends the block; subsequent calls replace in place.
- [ ] Cursor `.mdc` frontmatter is exactly what Cursor requires (test by inspection in a real Cursor install).

### Step 5.3 — `skillsmith watch` CLI

**Create** `src/skillsmith/install/subcommands/watch.py`.

| Command | Behavior |
|---|---|
| `skillsmith watch start [--harness X] [--profile X] [--detach]` | Start the watcher. Default harness is read from `~/.skillsmith/state.json`. `--detach` forks to background; otherwise foreground (useful for systemd / tmux). |
| `skillsmith watch stop` | Send SIGTERM to the running watcher (pidfile at `~/.skillsmith/watch/<profile>.pid`). |
| `skillsmith watch status` | Report whether a watcher is running for the current profile, last activity timestamp, last regeneration target. |

Detach implementation: use `os.fork()` + double-fork + `setsid`. Or recommend the user run it under systemd / launchd / tmux and don't implement detach. Recommend the latter for v1 (simpler, more reliable).

**Acceptance criteria:**

- [ ] `start` (foreground) runs the watcher and responds to SIGTERM.
- [ ] `status` correctly reports running/not-running.
- [ ] `stop` is idempotent (running again on a stopped watcher is a no-op).
- [ ] Watcher writes a pidfile and removes it on shutdown.

### Step 5.4 — Wire-harness changes for Tier 3

**Modify** `src/skillsmith/install/subcommands/wire_harness.py`.

When the user wires a Tier 3 harness:

1. Write `~/.skillsmith/watch/<profile>.yaml` with the watcher config.
2. Print:

```
[Skillsmith — Tier 3 wiring]
You selected: <harness>

Tier 3 harnesses do not support per-turn hooks. To get phase- and
contract-driven context updates, run the watcher sidecar:

    skillsmith watch start --harness <harness>

You can run this under your process manager of choice (systemd, launchd,
tmux, supervisord). Without the watcher, you'll only get the initial
workflow skill context that was present when you opened the harness;
mid-session phase changes won't be reflected.

System skills (governance like commit-safety) cannot be enforced on Tier
3 — they're included in the rules file as advisory text, but the harness
won't gate tool use on them.

See docs/tier3-experience.md for the full picture.
```

3. Optionally offer to install a launchd / systemd unit file (template provided under `tools/launch/`).

**Acceptance criteria:**

- [ ] Tier 3 wiring writes the watcher config.
- [ ] User cannot complete wiring without acknowledging the Tier 3 message (either by reading + pressing enter, or by passing `--non-interactive --acknowledge-tier3`).
- [ ] `~/.skillsmith/state.json` records the chosen harness and whether the watcher was started.

### Step 5.5 — README harness-support section

**Modify** `README.md`.

Add a section titled **"Harness support: what each tier gets"** containing a clear table:

```markdown
## Harness support: what each tier gets

Skillsmith routes context using per-turn hooks where the harness supports
them, and falls back to file-regeneration where it doesn't.

| Harness | Tier | Per-turn updates | Mid-session phase changes | System skills enforced | Setup notes |
|---|---|---|---|---|---|
| Claude Code | 1 | ✅ | ✅ | ✅ | Works out of the box after `skillsmith wire claude-code` |
| Continue.dev | 1 | ✅ | ✅ | ✅ | Requires custom context provider entry |
| Hermes Agent / SDK | 1 | ✅ | ✅ | ✅ | Programmatic injection in message build |
| Aider | 3 | ❌ | ⚠️ via `/read` re-issue | ⚠️ advisory only | Needs `skillsmith watch` sidecar |
| Cursor | 3 | ❌ | ✅ on file save | ⚠️ advisory only | Needs `skillsmith watch` sidecar |
| Windsurf | 3 | ❌ | ✅ on file save | ⚠️ advisory only | Needs `skillsmith watch` sidecar |
| GitHub Copilot (VS Code) | 3 | ❌ | ⚠️ requires reload | ⚠️ advisory only | Needs `skillsmith watch` sidecar |
| Cline | 3 | ❌ | ⚠️ requires reload | ⚠️ advisory only | Needs `skillsmith watch` sidecar |
| Gemini CLI | 3 | ❌ | ⚠️ requires new session | ⚠️ advisory only | Needs `skillsmith watch` sidecar |

**Tier 3 is a real reduction in capability.** If your work depends on
mid-session phase transitions or commit-safety gating, choose a Tier 1
harness. If you prefer your Tier 3 harness for other reasons, the
sidecar gets you most of the way there.
```

Then a one-paragraph block explaining the architecture, with a link to `docs/tier3-experience.md`.

**Acceptance criteria:**

- [ ] Table is visible in the top half of the README.
- [ ] "Tier 3 is a real reduction" sentence is **bold** (or otherwise unmissable).
- [ ] Links to the detailed Tier 3 experience doc.

### Step 5.6 — Tier 3 experience doc

**Create** `docs/tier3-experience.md`.

Audience: a user who picked a Tier 3 harness and wants to know exactly what they're getting.

Sections:

1. **What works (with the sidecar running):**
   - Phase transitions update the rules file on save → harness picks up on next read
   - Contract writes update the rules file with composed skills
   - Code-Indexer integration (Phase 4) also flows through the rules file
2. **What's degraded:**
   - System skills (commit-safety, secret-handling) are included as text, not gates. The harness won't refuse to commit.
   - Some harnesses need a workspace reload to pick up rules-file changes (Copilot, Cline, Gemini CLI). Sidecar regenerates correctly, but the model only sees the new content after reload.
   - No semantic predicate evaluation gating — gates that require Qwen classifier signals fall back to `UNKNOWN` and don't transition automatically. Phase transitions become manual via `skillsmith phase set <name>`.
3. **Why this is the right shape:**
   - Tier 3 harnesses are valuable for other reasons (IDE integration, team standards, license/cost). Skillsmith doesn't reject them; it gives them the best experience possible within their constraints.
4. **Operating the sidecar:**
   - `skillsmith watch start --harness <name>` (foreground recommendation; pair with tmux/systemd)
   - How to start at login (per-OS instructions)
   - Diagnosing stale rules files (`skillsmith watch status` + manual `touch .skillsmith/phase` to force regeneration)
5. **Choosing a Tier 1 harness instead:**
   - Quick comparison; pointers to Claude Code / Continue.dev quickstart.

**Acceptance criteria:**

- [ ] Reads end-to-end without referencing internal jargon.
- [ ] Includes a "do I need this?" decision tree at the top.
- [ ] Linked from README and from setup messaging.

### Step 5.7 — Setup-time messaging

**Modify** `src/skillsmith/install/subcommands/simple_setup.py`.

When the user reaches the harness-selection step and picks a Tier 3 harness, display a structured prompt:

```
⚠️  Tier 3 harness selected: <harness>

Skillsmith routes context best on harnesses with per-turn hooks. <harness>
doesn't have that capability, so Skillsmith uses a file-watching sidecar
to regenerate your harness's rules file on phase/contract changes.

This means:
  • Phase transitions: <handled by sidecar> ✅
  • Mid-session updates: <visible after harness reload/save> ⚠️
  • System skill enforcement (commit-safety, etc): advisory only ❌

Do you want to continue with <harness>?
  [y] Yes, set up Tier 3 with sidecar
  [c] Show me Tier 1 alternatives (Claude Code, Continue.dev)
  [n] Cancel setup

>
```

In non-interactive mode (`--non-interactive`), require explicit
`--acknowledge-tier3` flag. Without it, exit non-zero with the message above.

**Acceptance criteria:**

- [ ] Tier 3 selection prompts the user; default action is NOT proceed.
- [ ] Non-interactive setup blocks unless explicit acknowledgement.
- [ ] After acknowledgement, sidecar config is written and a final message reminds the user to start it.

## Tests to add

`tests/test_watch.py`:

- `test_phase_change_triggers_regenerate` — write `.skillsmith/phase` → expect regenerator called
- `test_contract_write_triggers_compose` — write contract → expect compose + regenerator
- `test_debounce_coalesces_burst_writes` — 10 rapid writes → 1 regeneration
- `test_regenerate_cursor_writes_valid_mdc` — file has correct frontmatter
- `test_update_block_preserves_user_content` — content before/after marker pair untouched
- `test_watch_status_reports_running` — start, then status, then stop

`tests/test_setup_tier3.py`:

- `test_tier3_selection_prompts_user` — interactive flow asks
- `test_tier3_non_interactive_requires_flag` — exit without `--acknowledge-tier3`
- `test_tier3_state_records_choice` — `state.json` reflects Tier 3

## Phase 5 integration test

**Goal:** verify the Tier 3 path works end to end with Cursor as the
reference Tier 3 harness.

Setup: Phases 1–3 complete (Phase 4 optional). A test repo at
`~/dev/test-repo` with Cursor installed.

Test scenario:

1. Run `skillsmith setup --non-interactive --harness cursor --acknowledge-tier3`. Confirm: `state.json` records Cursor.
2. Run `skillsmith wire cursor`. Confirm: `~/.skillsmith/watch/default.yaml` exists.
3. Start `skillsmith watch start --harness cursor` in a separate terminal (or `nohup ... &`).
4. In `~/dev/test-repo`, write `.skillsmith/phase` containing `phase: spec`.
5. Within 2 seconds: `.cursor/rules/skillsmith-context.mdc` exists with the spec workflow skill's prose and proper YAML frontmatter.
6. Write a contract at `.skillsmith/contracts/spec/test-task.md` with `domain_tags: ["python", "pytest"]`.
7. Within 2 seconds: `.cursor/rules/skillsmith-context.mdc` is updated; the prose now includes composed pytest+python skill fragments.
8. Open the test repo in Cursor (or simulate). Confirm Cursor reads the rules file.
9. Update `.skillsmith/phase` to `design`. Within 2 seconds: rules file updates to design workflow skill.
10. `skillsmith watch stop`. Confirm: watcher exits cleanly, pidfile removed.

If 1–10 pass, Phase 5 is complete and Skillsmith is shippable across all
supported harnesses.

## Known gotchas

- **`watchdog`** has platform-specific quirks (FSEvents on macOS, inotify on Linux). Test on both before declaring complete.
- **Rules-file reload latency varies by harness.** Cursor picks up changes on save in most cases; Copilot doesn't until workspace reopen. Document this per-harness.
- **Long-running watcher** can leak file handles if not carefully written. Use `watchdog`'s built-in cleanup; don't hand-roll inotify.
- **Profile changes during a running watcher.** If the user `cd`s into a repo that maps to a different profile, the existing watcher (started for profile X) keeps watching its project. Recommended: one watcher per profile per project, started explicitly. Don't try to auto-switch.
- **Marker-block conflicts** if another tool also writes to `copilot-instructions.md` or `GEMINI.md` with its own marker. Distinct markers per tool (SKILLSMITH-CONTEXT, CODE-INDEXER-CONTEXT, ...) prevent stomping. Document this clearly so future-tool authors follow the convention.
- **System skills as advisory text** in Tier 3 is genuinely weaker than gated enforcement. If a user expresses concern, the right answer is "Tier 1 harness" — don't try to compensate by making the advisory text scarier; that's not the architecture's job.
