# Skillsmith Context Reminder Provider

> **SUPERSEDED (2026-05-21).** Skillsmith no longer ships a reminder
> provider. The workflow skill injected at phase entry plus contract-driven
> domain retrieval (see `docs/signal-detection-and-domain-trigger-spec.md`)
> replace the need for per-turn language reminders.

Implements the per-turn context reminder pattern defined in
`docs/sdd-context-remind-hook-spec.md`. Read the pattern doc first — this
doc covers only what is specific to Skillsmith.

## Script

`tools/skillsmith-remind.sh` — version-controlled, ships with the
Skillsmith repo.

```bash
#!/usr/bin/env bash
# Skillsmith context reminder. Conforms to the per-turn context reminder
# contract (see docs/sdd-context-remind-hook-spec.md).
# Soft-fails — never blocks. Bounded (<1s).

set -u

# Self-locate the project root: walk up from this script's directory until
# we find a .git folder. Bindings do not need to set cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR"
while [[ "$ROOT" != "/" && ! -d "$ROOT/.git" ]]; do
    ROOT="$(dirname "$ROOT")"
done
cd "$ROOT" 2>/dev/null || exit 0

# Availability: skillsmith CLI must be installed and runnable.
command -v skillsmith >/dev/null 2>&1 || exit 0
skillsmith --version >/dev/null 2>&1 || {
    echo "[skillsmith] WARNING: skillsmith CLI not available. Run \`pip install -e .\` from the skillsmith repo."
    exit 0
}

# Gating: if a phase file exists, fire only in authoring/coding phases.
# If no phase file, fire unconditionally — the user installed skillsmith.
PHASE=""
if [[ -f ".skillsmith/phase" ]]; then
    PHASE=$(grep '^phase:' .skillsmith/phase 2>/dev/null | awk '{print $2}' | tr -d '"')
    case "$PHASE" in
        spec|design|build|qa) ;;       # fire
        *) exit 0 ;;                   # not a relevant phase
    esac
fi

PHASE_LINE=""
[[ -n "$PHASE" ]] && PHASE_LINE="Current phase: $PHASE"

cat <<EOF
[skillsmith] Skill packs are available for grounding this work.
Before authoring or implementing, check for relevant skills:
  skillsmith compose ${PHASE:+--phase $PHASE }--task "DESCRIBE YOUR TASK"
  skillsmith list --category CATEGORY
$PHASE_LINE
EOF

exit 0
```

## Gating

| Condition | Behavior |
|---|---|
| `skillsmith` CLI not installed | Silent exit (warns once if installed but broken) |
| Phase file present, phase ∈ {spec, design, build, qa} | Fire with phase line |
| Phase file present, other phase (ops, meta, governance, unknown) | Silent |
| No phase file | Fire unconditionally (no phase line) |

### Why fire in `spec`

Skill-pack lookup during spec authoring is the highest-value moment —
that's when patterns get chosen. Specs describe *what* should exist and
*why*; reaching for skills here informs the decision. (Contrast with
code-indexer, which deliberately stays out of `spec` to avoid leaking
implementation detail into specs.)

### Why fire when no phase file exists

Skillsmith is useful outside SDD-driven projects. A user who installs the
CLI and wires up the hook clearly wants the reminder. Silently emitting
nothing because they don't happen to have `.skillsmith/phase` would be a
worse default than always-on.

## Installation

Each binding below installs **only** the Skillsmith provider. To run
alongside Code-Indexer's provider, add its binding from
`code-indexer-service/docs/code-indexer-remind-provider.md`; the two
compose without further changes (see the pattern doc's Composition
section).

### Claude Code (Tier 1)

Append to `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "bash tools/skillsmith-remind.sh" }
        ]
      }
    ]
  }
}
```

### Continue.dev (Tier 1)

In `.continue/config.ts`:

```ts
export const skillsmithRemindProvider = {
  title: "skillsmith-context",
  description: "Skillsmith reminder",
  type: "normal",
  getContextItems: async () => {
    const { stdout } = await execAsync("bash tools/skillsmith-remind.sh");
    return stdout.trim()
      ? [{ name: "skillsmith-context", description: "reminder", content: stdout }]
      : [];
  },
};
```

### Tier 3 harnesses

Use the generated-rules pattern from the pattern doc with
`MARKER="SDD-CONTEXT-SKILLSMITH"`. The Skillsmith installer should provide
a `skillsmith install-hooks` command (or equivalent) that wires this up
for whichever harness the user selects.

## See also

- Pattern: `docs/sdd-context-remind-hook-spec.md`
- Code-Indexer provider (composes with this one): `code-indexer-service/docs/code-indexer-remind-provider.md`
