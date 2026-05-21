# Skill Authoring and Overrides

**Status:** Proposed
**Scope:** System skills and workflow skills only (whole-prose constructs).
Domain skills (fragmented, embedded for retrieval) remain centrally curated
and are explicitly **out of scope** for this spec.

## Decision summary

Bring authoring back into the standard Skillsmith runtime — but **only for
codified whole-prose skills** (system, workflow). Skillsmith installs
**once per user** and the harness wires it once; from then on every repo
the user works in gets Skillsmith capability without per-repo setup.

Users with multiple contexts (e.g., work + personal) get **profiles**:
named bundles of system/workflow overrides that the runtime auto-selects
based on the current repo's git remote or path. Domain skills are
universal — same industry packs (java, redshift, testing frameworks)
across every profile.

This preserves three invariants:

1. **Quality firewall on the retrieval corpus.** No user-side edits to
   domain fragments → embedding index, RRF weights, and reranker stay
   calibrated against a known corpus.
2. **Install once, work everywhere.** No per-repo wiring. New repos
   "just work" under whichever profile their remote matches.
3. **Customization where it matters.** Governance and workflow are
   context-specific (work rules ≠ personal rules ≠ client-X rules).
   Profiles make that explicit without forking the tool.

## Storage model

Three layers, one runtime authority.

### Layer 1 — Central defaults (shipped, read-only)

Lives inside the `skillsmith` package (e.g., `skillsmith/data/defaults/`).
Carries default system skills, default workflow skills, and the foundation
domain pack. Updated by upgrading the package.

### Layer 2 — Profile overrides (user-global, editable)

```
~/.skillsmith/
    profiles.yaml                            # profile detection rules
    domain.duck                              # shared domain corpus (never user-edited)
    profiles/
        work/
            skills.duck                      # resolved system+workflow for this profile
            skills/
                system/*.md                  # editable overrides
                workflow/*.md
        personal/
            skills.duck
            skills/{system,workflow}/*.md
        default/                             # built-in permissive profile
            skills.duck
            skills/{system,workflow}/*.md
```

The `default` profile is shipped and always present. It catches any repo
that doesn't match a configured profile and uses permissive defaults so
nothing is silently broken.

### Layer 3 — Project overrides (escape hatch, project-local)

```
<project>/.skillsmith/
    phase                                    # phase lock (always project-local)
    profile                                  # optional: force a specific profile
    skills/                                  # optional: per-project skill overrides
        system/*.md
        workflow/*.md
```

Rare in practice. Used when a single repo needs a tweak that doesn't
belong in the user's profile (often because the repo is shared with
others who don't use Skillsmith, or because the tweak is project-specific
team policy).

### Resolution order

Per skill: **project → profile → default**. First hit wins. No
intra-file merging.

The runtime never reads `*.md` files at query time — it reads the
**datastore** (`skills.duck` for the active profile, `domain.duck` for
shared domain). Files are the authoring artifact; the datastore is the
runtime authority. The bridge is `skillsmith author update`, which
validates and ingests.

## Profiles

### Detection

Three signals, evaluated in order. First match wins:

1. **Explicit project marker** — `<project>/.skillsmith/profile` containing
   `profile: <name>`. Wins if present. Escape hatch for repos that
   auto-detection picks wrong.
2. **Git remote URL pattern** — most stable signal. People reorganize
   directories; they rarely rewrite remotes.
3. **Path prefix** — fallback for non-git directories or repos with
   unrecognized remotes.

If no rule matches, falls back to the built-in `default` profile.
No error; the user gets permissive defaults until they configure better.

### Configuration

`~/.skillsmith/profiles.yaml`:

```yaml
profiles:
  work:
    match_remote:
      - "*github.com/acme-corp/*"
      - "*gitlab.acme.internal/*"
    match_path:
      - "~/work/**"
  personal:
    match_remote:
      - "*github.com/nmeyers/*"

default_profile: default       # used if nothing else matches
```

`match_remote` and `match_path` are both optional and both lists. A repo
matches a profile if **any** pattern in **either** list matches.

### What lives in a profile

Only system + workflow overrides. Profiles do **not** carry:

- Domain skill selection. All profiles see the same `domain.duck`.
- Embedding model choice or retrieval tuning. Those are global.
- Phase lock state. That's project-local.

If a user needs proprietary domain knowledge (internal frameworks, company-
specific patterns), the right home is either a System skill (whole-prose
governance) or the Code-Indexer / Knowledge-Decision Indexer — not a
private domain pack.

## File format

Markdown body with required YAML frontmatter. The validator enforces the
frontmatter shape; the prose body is author-controlled.

### Workflow skill

```markdown
---
type: workflow
name: sdd-spec
applies_to_phases: [spec]
exit_gates:
  - artifact_exists: docs/spec/*.md
  - artifact_contains:
      path: docs/spec/*.md
      sections: ["Acceptance Criteria", "Out of Scope"]
signal_keywords: ["done with spec", "ready to design", "next phase"]
---

# SDD Spec Phase

You are operating in the SDD spec phase. Your job is to ...
<persona / operating instructions, prose>
```

| Field | Required | Purpose |
|---|---|---|
| `type` | yes | Must be `workflow`. |
| `name` | yes | Stable identifier. Filename should match. |
| `applies_to_phases` | yes | Which phase(s) this skill is injected for. |
| `exit_gates` | yes | Declarative checklist Qwen evaluates to decide whether the phase can transition. Schema covered in the signal-detection spec (next). |
| `signal_keywords` | optional | Cheap prompt-text filters that might indicate phase completion; Qwen runs the gate check when one matches. |

### System skill

```markdown
---
type: system
name: commit-safety
applies_when:
  - tool_use_about_to_fire: ["git commit", "git push"]
  - phase_in: [build, qa]
---

# Commit Safety

Before any commit ...
<governance instructions, prose>
```

| Field | Required | Purpose |
|---|---|---|
| `type` | yes | Must be `system`. |
| `name` | yes | Stable identifier. |
| `applies_when` | yes | Applicability predicates. No ranking — gate-triggered. |

`applies_when` predicates are intentionally limited (no `ranked_by`, no
`semantic_match_against`) to keep this construct cheap and deterministic.

## Authoring CLI

Two subcommand groups: `skillsmith profile` for profile management and
`skillsmith author` for skill editing. All operations are local — no
central push.

### Profile management

| Command | What it does |
|---|---|
| `skillsmith profile list` | List configured profiles, marking the active one for the current cwd. |
| `skillsmith profile current` | Print the profile that resolves for the current cwd, plus the matching rule. |
| `skillsmith profile init <name>` | Create a new profile (empty overrides, prompts for `match_remote` / `match_path`). |
| `skillsmith profile set-default <name>` | Change the fallback profile. |
| `skillsmith profile delete <name>` | Delete a profile. Refuses if it's the default. |

### Skill authoring

The `--profile <name>` flag targets a specific profile; default is the
profile that resolves for the current cwd. `--project` targets the
project-local escape-hatch layer instead.

| Command | What it does |
|---|---|
| `skillsmith author list [--profile X]` | List system + workflow skills, marking which have overrides at each layer. |
| `skillsmith author edit <name> [--profile X \| --project]` | Open the override in `$EDITOR`. If no override exists at the target layer, copy from the next-higher layer first. |
| `skillsmith author validate <name> [--profile X \| --project]` | Lint: frontmatter schema, required sections, gate predicate syntax. Exit non-zero on failure. |
| `skillsmith author update <name> [--profile X \| --project]` | Validate, then ingest into the appropriate datastore. No-op if the override is unchanged from the layer below (deletes the override, notes "reverted to inherited"). |
| `skillsmith author diff <name>` | Show diff between current effective version and inherited (next-layer-down). |
| `skillsmith author reset <name> [--profile X \| --project]` | Delete the override at the target layer. Prompts for confirmation. |
| `skillsmith author update --all [--profile X]` | Re-ingest every authorable skill for a profile. Used by setup and after package upgrades. |

Domain skills are intentionally absent from `author`. Attempting
`skillsmith author edit pytest-testing` errors with a pointer to the
central pack maintainer process.

## Update flow

End-to-end loop for customizing a workflow skill in the current profile:

1. `skillsmith author edit sdd-spec` — opens the file (copying from default into the profile override location if needed).
2. User (or their paid LLM) edits the prose and/or gates.
3. `skillsmith author validate sdd-spec` — surfaces frontmatter/schema errors.
4. `skillsmith author update sdd-spec` — pushes the new version into the profile's `skills.duck`.
5. Next phase transition into `spec` for any repo in this profile picks up the new version. Repos in *other* profiles are unaffected.

No service restart. Datastore writes are atomic.

## Setup integration

`skillsmith setup` runs **once per user**, not once per repo:

1. Create `~/.skillsmith/` if missing.
2. Initialize the shipped `default` profile + its `skills.duck`.
3. Ingest central defaults (system, workflow, foundation domain) — system+workflow into the default profile's `skills.duck`, foundation domain into the shared `domain.duck`.
4. Write a starter `profiles.yaml` with `default_profile: default` and a commented example.
5. Wire the harness (one of `wire-harness claude-code`, `wire-harness cursor`, etc.) — points the harness at the user-global install.

After setup, new repos require **no Skillsmith setup of any kind**.
Auto-detection picks the profile from remote/path; `.skillsmith/phase`
is created on first phase transition.

Adding a new profile post-setup:

1. `skillsmith profile init work`
2. Configure `match_remote` / `match_path` (prompted by `init`, or edit `profiles.yaml` directly).
3. `skillsmith author edit --profile work sdd-spec` (or any other authorable).
4. `skillsmith author update --profile work --all`.

## Validation rules (mandatory)

Validator MUST reject a workflow skill that lacks `exit_gates`. Without
gates, the signal-detection layer cannot decide phase transitions — the
skill would inject correctly at phase entry but the system could never
leave that phase except by manual override. Highest-leverage authoring
failure mode; warrants a hard stop.

Validator MUST reject a system skill that lacks `applies_when`. A system
skill with no applicability is either always-on (use a workflow skill
instead) or never-on (delete it).

Soft warnings (validator emits but does not block):

- Workflow skill body shorter than ~200 words. Probably under-specified.
- `signal_keywords` empty. Phase transitions will rely entirely on artifact/state signals — may be intentional but worth confirming.
- Gate references an artifact path that does not exist anywhere in the current repo at validation time. May be authored ahead of the workflow.

## Out of scope (deferred)

- **Gate predicate semantics and the Qwen evaluation loop.** Covered in the next spec (signal detection).
- **Domain skill trigger.** Sticky domain lock + delta detection. Shares signal-detection mechanism.
- **Author publish / share.** Could send a workflow skill back to a central registry for team-wide adoption. Not addressed here.
- **Knowledge / Decision indexer integration.** A planned third tool for proprietary, internal knowledge that doesn't fit the universal-domain or governance-system models. Will compose with Skillsmith via the same reminder/injection pattern but is independently scoped.

## Design decisions

**Why install-once / user-global instead of per-repo?**
Per-repo wiring is friction for a tool that should be ambient. The user
already wired Skillsmith into their harness — the harness sees every repo
that user works in. There's nothing to re-wire per repo.

**Why profiles instead of per-repo config?**
Most users have a small number of contexts (work, personal, maybe a
specific client) and many repos per context. Per-repo config means
editing the same thing in N places. Per-profile config edits once.

**Why detect by git remote first?**
Path layouts get reorganized constantly; git remotes almost never
change. Most stable signal.

**Why a built-in `default` profile?**
Unmatched repos must do something. Erroring is hostile to first-run
experience; falling through to permissive defaults lets the tool work
out of the box and the user opts into stricter profiles as they
configure them.

**Why a `default_profile` setting if there's a built-in default?**
Some users will want their personal profile to be the unmatched fallback,
not the built-in. `default_profile: personal` swaps that.

**Why no per-profile domain selection?**
Domain packs are industry knowledge (java, pytest, redshift). They're
universal by definition. Profiles are about *context-specific behavior*
(governance, workflow gates), not about what knowledge exists. If a
user needs internal/proprietary knowledge, that's a System skill or a
Code-Indexer / Knowledge-Decision indexer concern, not a private
domain pack — which would degrade the universally-curated corpus.

**Why prose files with frontmatter instead of pure YAML/JSON?**
The persona/instructions ARE the skill. They want to be markdown,
edited by humans or paid LLMs that natively write markdown. Frontmatter
carries the structured fields the runtime needs.

**Why is the datastore authoritative if files are the source of truth?**
Files are the source for authoring; the datastore is the source for
runtime. Decoupling them gives an explicit "publish" step
(`author update`) where validation runs. You can't accidentally break
the runtime by saving a half-edited markdown file.

**Why is domain authoring excluded?**
Quality of the retrieval corpus depends on consistent embedding inputs,
consistent metadata, consistent fragment shape. One user editing
fragments degrades retrieval for every other use of the same pack.
Domain authoring stays in maintainer tooling.
