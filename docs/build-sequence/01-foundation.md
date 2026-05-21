# Phase 1: Foundation

**Prerequisites:** Read `docs/skill-authoring-and-overrides-spec.md` and
`docs/build-sequence/00-index.md`.

**Goal:** Skillsmith installs once per user, auto-detects the right profile
per repo, and exposes a `customize` CLI for editing system/workflow skills.
After this phase, every existing skillsmith feature still works; profiles
become the active context for system + workflow skill resolution.

**Done means:** all acceptance criteria below pass AND the integration test
at the end of this doc passes.

## Files to create

| Path | Purpose |
|---|---|
| `src/skillsmith/profiles.py` | Profile resolver + datastore-per-profile manager |
| `src/skillsmith/install/subcommands/profile.py` | `skillsmith profile {list,current,init,set-default,delete}` |
| `src/skillsmith/install/subcommands/customize.py` | `skillsmith customize {list,edit,validate,update,diff,reset}` |
| `src/skillsmith/install/subcommands/reset.py` | `skillsmith reset` (new — distinct from existing `reset_step.py`) |
| `tests/test_profiles.py` | Unit + integration tests for resolver and CLI |
| `tests/test_customize.py` | Tests for customize CLI workflow |

## Files to modify

| Path | What changes |
|---|---|
| `src/skillsmith/install/__main__.py` | Register `profile`, `customize`, `reset` subcommands in `_SUBCOMMANDS` list (lines 59-92) |
| `src/skillsmith/install/subcommands/simple_setup.py` | Add refuse-if-existing check; emit profile-aware completion message |
| `src/skillsmith/install/subcommands/update.py` | Add default-reingest step that preserves overrides |
| `src/skillsmith/config.py` | Add `profile_root` setting; expose profile-resolved datastore path |
| `src/skillsmith/runtime_state.py` | Honor active profile when loading the runtime cache |

## Step-by-step

### Step 1.1 — Profile resolver

**Create** `src/skillsmith/profiles.py`.

Public API:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Profile:
    name: str
    skills_dir: Path          # ~/.skillsmith/profiles/<name>/skills/
    datastore_path: Path      # ~/.skillsmith/profiles/<name>/skills.duck
    is_default: bool          # True if this is the built-in `default` profile

@dataclass(frozen=True)
class ProfilesConfig:
    profiles: dict[str, dict]   # raw config from profiles.yaml
    default_profile: str        # name of fallback profile

def profiles_root() -> Path:
    """Return ~/.skillsmith/ (honoring XDG)."""

def load_profiles_config() -> ProfilesConfig:
    """Load ~/.skillsmith/profiles.yaml. Returns default config if missing."""

def detect_profile(cwd: Path | None = None) -> Profile:
    """Resolve the active profile for cwd in priority order:
    1. <project>/.skillsmith/profile (explicit marker)
    2. Match git remote against profiles.yaml `match_remote`
    3. Match cwd path against profiles.yaml `match_path`
    4. Fall back to `default_profile`
    """

def list_profiles() -> list[Profile]:
    """All configured profiles plus the built-in `default`."""

def get_profile(name: str) -> Profile:
    """Look up by name. Raises KeyError if not configured."""

def init_profile(name: str, match_remote: list[str] | None, match_path: list[str] | None) -> Profile:
    """Create a new profile directory + datastore + profiles.yaml entry."""

def delete_profile(name: str) -> None:
    """Remove the profile directory and config entry. Refuses if name == default."""

def domain_datastore_path() -> Path:
    """The shared domain datastore (~/.skillsmith/domain.duck)."""
```

Notes:
- The `default` profile is always present; if `profiles.yaml` is missing or has no entries, every detection resolves to `default`.
- `match_remote` patterns use `fnmatch` glob syntax against the output of `git remote get-url origin`.
- `match_path` patterns expand `~` and use `pathlib.Path.match` against the absolute cwd.
- The function `detect_profile` must be cheap (<10ms) — called on every retrieval and every hook fire.

**Acceptance criteria:**

- [ ] All public API functions implemented with type hints.
- [ ] `detect_profile` correctly handles: explicit marker → remote match → path match → default.
- [ ] `init_profile` creates `~/.skillsmith/profiles/<name>/skills/{system,workflow}/` and an empty `skills.duck`.
- [ ] `delete_profile("default")` raises ValueError.
- [ ] `domain_datastore_path()` returns a path independent of profile.

### Step 1.2 — Update config layer

**Modify** `src/skillsmith/config.py`.

Add to `Settings`:

```python
# Profile root. Resolves to ~/.skillsmith by default.
profile_root: str = Field(default_factory=lambda: str(Path.home() / ".skillsmith"))

# When set, overrides auto-detection (useful for tests).
forced_profile: str | None = None
```

Add a helper method:

```python
def active_datastore_path(self, cwd: Path | None = None) -> Path:
    """Return the skills.duck for the active profile.

    Falls back to the legacy `duckdb_path` when `profile_root` is unset
    OR when the active profile has no datastore yet (first-run grace).
    """
```

**Acceptance criteria:**

- [ ] Existing `duckdb_path` remains as a fallback; existing deployments don't break.
- [ ] `active_datastore_path()` returns the profile-resolved path when a profile is detected.
- [ ] All callers of `settings.duckdb_path` either switch to `active_datastore_path()` (Phase 1 deliverable) or are explicitly marked "legacy callers — Phase 2/3 will migrate."

### Step 1.3 — `skillsmith profile` subcommand

**Create** `src/skillsmith/install/subcommands/profile.py` following the existing subcommand pattern (see `simple_setup.py:add_parser` and `run`).

Commands and behavior:

| Command | Behavior |
|---|---|
| `skillsmith profile list` | JSON output: `[{name, active_for_cwd, match_remote, match_path, has_overrides}]` |
| `skillsmith profile current` | JSON: `{name, matched_rule, datastore_path}` |
| `skillsmith profile init <name>` | Prompts for match patterns interactively; non-interactive flag `--match-remote PATTERN --match-path PATTERN` supported |
| `skillsmith profile set-default <name>` | Updates `default_profile` in `profiles.yaml` |
| `skillsmith profile delete <name>` | Confirms, then removes dir + config entry. Refuses on `default`. |

**Acceptance criteria:**

- [ ] All five subcommands implemented and registered in `install/__main__.py`.
- [ ] JSON output by default; `--human` flag toggles a rich-printed alternative.
- [ ] `profile current` returns the same `Profile` that `detect_profile()` would return.
- [ ] Tests cover round-trip (init → list → set-default → delete).

### Step 1.4 — `skillsmith customize` subcommand

**Create** `src/skillsmith/install/subcommands/customize.py`.

Three-layer resolution (per `skill-authoring-and-overrides-spec.md`):
1. Project: `<project>/.skillsmith/skills/{system,workflow}/<name>.md`
2. Profile: `~/.skillsmith/profiles/<profile>/skills/{system,workflow}/<name>.md`
3. Default: shipped in package at `src/skillsmith/_packs/<class>/<name>.{yaml,md}`

Commands:

| Command | Behavior |
|---|---|
| `skillsmith customize list [--profile X]` | JSON: skills + which layer each comes from |
| `skillsmith customize edit <name> [--profile X \| --project]` | Opens `$EDITOR` on the override path. Copies from next-higher layer if no override exists at target. |
| `skillsmith customize validate <name> [--profile X \| --project]` | Validates frontmatter + body. Exit non-zero on failure with structured error. |
| `skillsmith customize update <name> [--profile X \| --project]` | Validates, then ingests into the target datastore. No-op if unchanged from inherited; deletes the override if identical (logs "reverted to inherited"). |
| `skillsmith customize diff <name>` | Unified diff vs next-higher layer |
| `skillsmith customize reset <name> [--profile X \| --project]` | Deletes the override (with confirmation) |
| `skillsmith customize update --all [--profile X]` | Re-ingests all customized skills. Used by `setup` and `update`. |

**Important:** the existing `_packs/<name>.yaml` files have `skill_class` set per file. The customize CLI only acts on `skill_class` ∈ {`system`, `workflow`}. Attempting `customize edit pytest-testing` (which is `skill_class: domain`) MUST error with:

```
[error] customize is for system+workflow skills only. 'pytest-testing' is a domain skill (centrally curated). See docs/skill-authoring-and-overrides-spec.md.
```

**Validation rules** (per spec):

- `skill_class` must be `system` or `workflow`
- Workflow skill MUST have `applies_to_phases` (list) and `exit_gates` (object — see Phase 2 for schema; for Phase 1, accept any non-empty object)
- System skill MUST have `applies_when` (object — see Phase 2 for schema)
- Body MUST be ≥ 80 characters (catches empty stubs)

**Format decision:** keep YAML (existing format), but make `raw_prose` field semantically equivalent to the markdown body in our spec. Customize CLI edits the YAML file directly with `$EDITOR`. Format conversion to markdown+frontmatter is a future migration, deferred.

**Acceptance criteria:**

- [ ] All seven subcommands implemented.
- [ ] Three-layer resolution works in `list` output.
- [ ] `validate` rejects malformed YAML, missing required fields, and `skill_class: domain` targets.
- [ ] `update` ingests into the profile datastore (or project, with `--project`); does not pollute the shared domain datastore.
- [ ] `update --all` is what `setup` and `update` call to seed/refresh.

### Step 1.5 — Refactor `skillsmith setup` to be profile-aware + refuse-if-existing

> **Sequencing prerequisite:** `SETUP_WIZARD_UX_SPEC.md` (in the repo root)
> must land **before** this step. That spec is a focused UX/bug-fix cluster
> for `simple_setup.py` (numbered menus, runner-sentinel fix, hardware
> label map, flow reorder). Its line references assume the pre-refactor
> state of the file. Phase 1's profile-awareness changes layer on top of
> the cleaned-up wizard.
>
> If you land Phase 1 first, the SETUP_WIZARD line references go stale
> and that PR becomes much harder to review.

**Modify** `src/skillsmith/install/subcommands/simple_setup.py`.

Changes:

1. At wizard start, call `profiles.detect_profile(cwd)`. If `~/.skillsmith/profiles.yaml` doesn't exist, create it with the built-in `default` entry only.
2. Before any state-mutating step, check `profiles.get_profile(name).datastore_path.exists()`. If the datastore already exists with ingested skills:
   - Print: `Skillsmith is already initialized for profile '<name>' (datastore: <path>). Use 'skillsmith update' to refresh defaults or 'skillsmith reset' to wipe and reinstall.`
   - Exit with `EXIT_NOOP` (4).
3. On first install, run the existing wizard but route seed/ingest steps through `profiles.get_profile(default).datastore_path` instead of `settings.duckdb_path`.
4. At completion, print profile information: which profile is active, where the datastore lives, and a pointer to `skillsmith customize`.

**Acceptance criteria:**

- [ ] First-run setup creates `~/.skillsmith/profiles/default/skills.duck` and ingests defaults.
- [ ] Second-run setup detects the existing datastore and exits 4 with the "already initialized" message.
- [ ] `skillsmith setup --force` flag (new) bypasses the existence check — useful for development, dangerous in prod (prompts for confirmation).
- [ ] Existing setup tests still pass (or are updated to expect profile-aware behavior).

### Step 1.6 — Enhance `skillsmith update` to re-ingest defaults preserving overrides

**Modify** `src/skillsmith/install/subcommands/update.py`.

After the existing steps (git/schema/integrity/model-drift), add:

5. **Default re-ingest with override preservation.** For each shipped default skill (`_packs/*` with `skill_class` in {system, workflow}):
   a. Compute hash of the shipped default.
   b. Look up the corresponding row in the active profile's datastore.
   c. Look up the corresponding override file in `~/.skillsmith/profiles/<name>/skills/` and `<project>/.skillsmith/skills/` (if applicable).
   d. Decision matrix:
      | Datastore hash | Override exists | Action |
      |---|---|---|
      | matches old default | no | Replace with new default (silent) |
      | matches old default | yes (override unchanged from old default) | Replace override + datastore with new default (log "auto-merged") |
      | differs (user customized via update workflow) | no | Skip (user has customized) |
      | differs | yes | Prompt: `[skill X] default has changed. Your override may be stale. Diff? (y/n)`. Default action: skip with note. |

6. Output a summary: `{auto_merged: [...], skipped_due_to_override: [...], conflicts: [...]}`.

**Acceptance criteria:**

- [ ] `update` is idempotent: re-running with no shipped changes is a no-op.
- [ ] Overridden skills are never silently overwritten.
- [ ] User-prompted conflicts default to "skip" (preserve override).
- [ ] Summary JSON is written to `~/.skillsmith/last-update.json` for audit.

### Step 1.7 — Implement `skillsmith reset`

**Create** `src/skillsmith/install/subcommands/reset.py`.

Distinct from the existing `reset_step.py` (which resets a single install step). The new `reset` is the nuclear option:

| Flag | Behavior |
|---|---|
| `skillsmith reset` | Prompts for confirmation. Deletes overrides for the active profile (system + workflow), re-ingests defaults. Domain datastore untouched. |
| `skillsmith reset --profile <name>` | Targets a specific profile. |
| `skillsmith reset --all-profiles` | Resets every profile. Strong confirmation prompt. |
| `skillsmith reset --include-domain` | Also wipes and re-ingests `~/.skillsmith/domain.duck`. Slow (full re-embed). |
| `skillsmith reset --yes` | Skip confirmation (dangerous; for scripts). |

Output: JSON summary of what was reset.

**Acceptance criteria:**

- [ ] `reset` (no flags) requires explicit confirmation (typed "yes" or `--yes`).
- [ ] After reset, the profile's datastore matches what `setup` produces.
- [ ] `reset` does not touch other profiles unless `--all-profiles` is passed.
- [ ] `reset` does not touch the domain datastore unless `--include-domain` is passed.

### Step 1.8 — Update runtime cache to honor active profile

**Modify** `src/skillsmith/runtime_state.py`.

The runtime cache (`RuntimeCache`) currently loads from a single datastore.
Change the constructor to accept a profile name; cache key includes the
profile. On profile change between requests (rare but possible if a
user switches repos in the same session), invalidate and reload.

**Acceptance criteria:**

- [ ] `RuntimeCache.for_profile(name: str)` factory method.
- [ ] Single-process can hold multiple profile caches simultaneously (LRU bounded; e.g. max 4).
- [ ] Tests cover: load profile A → load profile B → verify A's skills are not visible.

## Tests to add

`tests/test_profiles.py`:

- `test_detect_profile_explicit_marker` — `.skillsmith/profile` file wins
- `test_detect_profile_remote_match` — git remote URL matches a configured pattern
- `test_detect_profile_path_match` — cwd path matches when remote doesn't
- `test_detect_profile_fallback_to_default` — no match → built-in default
- `test_init_profile_creates_structure` — directories + datastore + config entry
- `test_delete_default_refused` — `delete_profile("default")` raises
- `test_domain_datastore_independent_of_profile` — same path regardless of active profile

`tests/test_customize.py`:

- `test_customize_list_three_layers` — output shows correct provenance per skill
- `test_customize_edit_copies_from_default` — first edit copies default into override
- `test_customize_validate_rejects_domain` — `customize edit <domain-skill>` errors
- `test_customize_validate_required_fields` — workflow missing `exit_gates` rejected
- `test_customize_update_ingests_into_profile` — datastore row matches edited content
- `test_customize_update_reverts_to_inherited` — identical content → override deleted

`tests/test_install_setup.py` (modify existing):

- `test_setup_refuses_if_existing_datastore` — second run exits 4
- `test_setup_force_bypasses_check` — `--force` proceeds

`tests/test_install_update.py` (modify existing):

- `test_update_preserves_user_override` — modified override is not overwritten
- `test_update_auto_merges_unchanged_override` — override matching old default is updated
- `test_update_prompts_on_conflict` — diverged override + new default → prompt

`tests/test_install_reset.py` (new):

- `test_reset_requires_confirmation` — no `--yes` → prompt
- `test_reset_clears_profile_overrides` — overrides gone, defaults restored
- `test_reset_does_not_touch_domain` — domain datastore unchanged
- `test_reset_include_domain_re_embeds` — slow but works

## Phase 1 integration test

**Goal:** verify the full foundation works end to end without touching
Phases 2–5.

Test scenario:

1. Fresh user: no `~/.skillsmith/`.
2. Run `skillsmith setup --non-interactive --runner ollama --harness manual` (existing flags).
3. Assert: `~/.skillsmith/profiles/default/skills.duck` exists with all `_packs/*.yaml` skills ingested. `~/.skillsmith/domain.duck` exists with domain pack skills.
4. Run `skillsmith profile current` from cwd. Assert: returns `default`.
5. Run `skillsmith profile init work --match-remote "*github.com/acme/*"`.
6. cd into a repo with remote `github.com/acme/foo.git`. Run `skillsmith profile current`. Assert: returns `work`.
7. Run `skillsmith customize edit sdd-spec-and-scoping --profile work` (in a non-interactive test, write the edit programmatically). Assert: file appears at `~/.skillsmith/profiles/work/skills/workflow/sdd-spec-and-scoping.yaml`.
8. Run `skillsmith customize update sdd-spec-and-scoping --profile work`. Assert: the row in `work/skills.duck` reflects the edit.
9. Run `skillsmith update`. Assert: `work`'s override is preserved.
10. Run `skillsmith reset --profile work --yes`. Assert: override file is gone; datastore row matches default.

If all 10 steps pass, Phase 1 is complete. Move to Phase 2.

## Known gotchas

- **`skill_class` for SDD skills currently says `domain`.** The existing files in `_packs/sdd/` are tagged `skill_class: domain`. Decide in Phase 2 whether to retag them as `workflow` (likely yes — they ARE workflow skills by our new typology) or to add a separate `workflow_role` field. Phase 2 will need them as `workflow` to fire workflow-skill injection on phase change. For Phase 1, leave them as-is — `customize` allowing both is fine for now.
- **Existing `phase.py` subcommand** (`install/subcommands/phase.py`) manipulates a phase concept already. Read it before Phase 3 — it may overlap with the signal layer's phase-lock semantics. We may absorb it or leave it as a manual-override tool.
- **`authoring/` collision.** Don't add `customize` logic into `authoring/`; keep it separate. `authoring/` is maintainer-side LLM skill generation; `customize` is user-side markdown editing.
- **Verify whether `src/skillsmith/authoring/` in the main repo is still needed.** The `skillsmith-authoring` repo (`~/dev/skillsmith-authoring/`) now ships the same module names (`driver`, `pipeline`, `qa_gate`, `dedup`, `prompt_loader`) as a standalone authoring pipeline. The in-repo `authoring/` directory may be legacy from before that extraction. During Phase 1, confirm with the maintainer whether to delete it — leaving both around invites confusion with the user-facing `customize` CLI added in this phase.
