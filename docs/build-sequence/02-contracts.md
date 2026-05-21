# Phase 2: Contracts

**Prerequisites:** Phase 1 complete. Read `docs/signal-detection-and-domain-trigger-spec.md`.

**Goal:** The paid LLM can write a per-task contract following the active
workflow skill's template, Skillsmith validates and consumes it, and
domain retrieval uses the contract's `domain_tags` as BM25 input. After
this phase, contract-driven retrieval works end to end via a manual
trigger (`skillsmith compose --contract <path>`); automatic triggering
comes in Phase 3.

**Done means:** all acceptance criteria below pass AND the integration
test at the end passes.

## Files to create

| Path | Purpose |
|---|---|
| `src/skillsmith/contracts.py` | Contract parsing, validation, dataclass |
| `src/skillsmith/install/subcommands/contract.py` | `skillsmith contract {validate,show,init}` |
| `tests/test_contracts.py` | Contract parsing + validation tests |
| `tests/test_retrieval_with_contract.py` | BM25-modification end-to-end tests |

## Files to modify

| Path | What changes |
|---|---|
| `src/skillsmith/api/compose_models.py` | Add optional `contract_path` field to `ComposeRequest` (and downstream `contract_tags` resolution) |
| `src/skillsmith/api/compose_router.py` | If `contract_path` provided, load contract → populate `domain_tags` → call orchestrator |
| `src/skillsmith/orchestration/compose.py` | Accept resolved `domain_tags` from contract; pass through to retrieval |
| `src/skillsmith/retrieval/domain.py` | Modify BM25 query construction to prefer contract tags when provided (line ~227) |
| `src/skillsmith/_packs/sdd/sdd-*.yaml` | Retag `skill_class: domain` → `skill_class: workflow`; add `applies_to_phases`, `exit_gates` (Phase 2: minimal/stub gates), `contract_template` prose |
| `src/skillsmith/install/subcommands/customize.py` | Tighten validator (added in Phase 1) to require workflow `exit_gates` schema + `contract_template` |
| `src/skillsmith/install/__main__.py` | Register `contract` subcommand |

## Step-by-step

### Step 2.1 — Contract dataclass + parser

**Create** `src/skillsmith/contracts.py`.

Public API:

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

@dataclass(frozen=True)
class ContractScope:
    touches: list[str]           # globs; may be empty
    avoids: list[str]            # globs; may be empty

@dataclass(frozen=True)
class Contract:
    path: Path                    # absolute path to the contract file
    phase: str                    # required
    task_slug: str                # required
    domain_tags: list[str]        # required, non-empty
    scope: ContractScope          # may have empty lists but field is present
    success_criteria: list[str]   # may be empty
    related_contracts: list[Path] # may be empty
    created_at: datetime | None   # optional; falls back to file mtime
    body: str                     # the markdown body below frontmatter

class ContractError(Exception):
    """Base for contract problems."""

class ContractMalformed(ContractError):
    """Frontmatter missing, schema invalid, etc."""

class ContractPhaseMismatch(ContractError):
    """Contract's `phase` field doesn't match .skillsmith/phase."""

def parse_contract(path: Path) -> Contract:
    """Read + validate. Raises on malformed or schema violations."""

def validate_contract(contract: Contract, project_root: Path) -> list[str]:
    """Return list of issues (empty = valid). Checks:
       - phase matches .skillsmith/phase (if present)
       - referenced related_contracts files exist
       - domain_tags non-empty
       - scope.touches globs are valid syntax
    """

def list_contracts_for_phase(project_root: Path, phase: str) -> list[Path]:
    """Return all .skillsmith/contracts/<phase>/*.md in mtime descending order."""

def latest_contract(project_root: Path, phase: str | None = None) -> Path | None:
    """Most recently modified contract for the phase (or any phase if None)."""
```

Format (matches spec):

```markdown
---
phase: build
task_slug: add-auth-middleware
domain_tags:
  - NestJS
  - Express middleware
  - JWT validation
scope:
  touches:
    - "src/auth/**"
    - "tests/auth/**"
  avoids:
    - "src/billing/**"
success_criteria:
  - "Existing auth tests still pass"
related_contracts: []
created_at: 2026-05-21T14:32:11Z
---

# Add Auth Middleware

<task description prose>
```

Parser uses `python-frontmatter` or equivalent (already in deps? check `pyproject.toml`). If not present, add it as a dependency.

**Acceptance criteria:**

- [ ] `parse_contract` round-trips a well-formed example without information loss.
- [ ] `parse_contract` raises `ContractMalformed` with a clear message for: missing frontmatter, missing required fields, wrong types, empty `domain_tags`.
- [ ] `validate_contract` returns issues without raising; caller decides whether to proceed.
- [ ] `list_contracts_for_phase` returns paths sorted newest-first by mtime.

### Step 2.2 — `skillsmith contract` subcommand

**Create** `src/skillsmith/install/subcommands/contract.py`.

| Command | Behavior |
|---|---|
| `skillsmith contract validate <path>` | Runs `parse_contract` + `validate_contract`. JSON output with issues list. Exit non-zero if any issues. |
| `skillsmith contract show <path>` | Pretty-print parsed contract (JSON or human format) |
| `skillsmith contract init --phase <name> --slug <slug>` | Scaffold a contract from the active workflow skill's `contract_template`. Writes to `.skillsmith/contracts/<phase>/<slug>.md` and prints the path. Refuses if file exists (use `--force` to overwrite). |

`contract init` is what the paid LLM calls (via the harness's Bash tool) when the workflow skill instructs it to "scaffold a contract." It returns a populated template the LLM then fills in.

**Acceptance criteria:**

- [ ] `contract validate` exit-0 for valid contract, non-zero for invalid.
- [ ] `contract init` reads `contract_template` from the active workflow skill (resolved through the profile datastore) and substitutes `{{phase}}`, `{{task_slug}}`, `{{created_at}}`.
- [ ] `contract init` errors clearly if no active workflow skill is found for the current phase.

### Step 2.3 — Workflow skill schema: contract template + gates

**Modify** `src/skillsmith/_packs/sdd/sdd-spec-and-scoping.yaml` and siblings.

Required new fields (per `skill-authoring-and-overrides-spec.md`):

```yaml
skill_class: workflow         # changed from "domain"
applies_to_phases: [spec]     # one phase per workflow skill; lists allowed
exit_gates:
  all_of:
    - artifact_exists:
        path: "docs/spec/*.md"
    - artifact_contains:
        path: "docs/spec/*.md"
        sections: ["Acceptance Criteria", "Out of Scope"]
    # Phase 2: deterministic gates only. Phase 3 adds semantic gates.
signal_keywords:
  - "done with spec"
  - "ready to design"
  - "next phase"
contract_template: |
  ---
  phase: spec
  task_slug: {{task_slug}}
  domain_tags: []
  scope:
    touches: []
    avoids: []
  success_criteria: []
  related_contracts: []
  created_at: {{created_at}}
  ---

  # {{task_slug | titlecase}}

  ## Task description
  <fill in what you intend to do and why>
```

Map each phase to a workflow skill:

| Phase | Workflow skill file |
|---|---|
| `spec` | `sdd-spec-and-scoping.yaml` |
| `design` | `sdd-design-and-planning.yaml` |
| `build` | (NEW — does not exist today; create as `sdd-build.yaml`) |
| `qa` | `sdd-verify-and-review.yaml` |
| `ship` | `sdd-deliver-and-ship.yaml` |

Note that today the four existing SDD files don't include a `build` phase as a discrete file. Decide: either reuse design or verify for build, OR introduce `sdd-build.yaml`. Recommend introducing it for symmetry with the SDD phase model (spec / design / build / qa / ship).

**Acceptance criteria:**

- [ ] All sdd-* YAML files have `skill_class: workflow`.
- [ ] Each has `applies_to_phases`, `exit_gates`, `signal_keywords`, `contract_template`.
- [ ] Phase-to-file map is documented in `_packs/sdd/pack.yaml`.
- [ ] `customize validate` accepts the new schema.
- [ ] `customize validate` REJECTS a workflow skill missing `contract_template` or `exit_gates`.

### Step 2.4 — Domain retrieval: consume contract tags as BM25 input

**Modify** `src/skillsmith/retrieval/domain.py` around line 227-230.

Current code:

```python
# Rule-based keyword extraction for BM25 boosting
bm25_query = _extract_bm25_keywords(task)
```

Target:

```python
# When a contract provides domain_tags, those become the BM25 query.
# The paid LLM picked them deliberately; they're better keywords than
# rule-extracted ones. Optionally union with rule-extracted via env var.
if contract_tags:
    bm25_query = " ".join(contract_tags)
    if os.environ.get("SKILLSMITH_UNION_KEYWORDS") == "1":
        bm25_query += " " + _extract_bm25_keywords(task)
else:
    bm25_query = _extract_bm25_keywords(task)
```

This requires plumbing `contract_tags: list[str] | None` through:
- `retrieve_domain_candidates()` signature in `retrieval/domain.py`
- `ComposeOrchestrator.retrieve()` in `orchestration/compose.py:166`
- `ComposeRequest` in `api/compose_models.py`

Add request field:

```python
class ComposeRequest(BaseModel):
    # existing fields...
    contract_path: Path | None = None     # optional; if set, loads contract
    contract_tags: list[str] | None = None # if set explicitly, bypasses contract load

    @property
    def resolved_contract_tags(self) -> list[str] | None:
        if self.contract_tags is not None:
            return self.contract_tags
        if self.contract_path is not None:
            from skillsmith.contracts import parse_contract
            return parse_contract(self.contract_path).domain_tags
        return None
```

**Phase RRF weights**: keep existing phase-specific weights logic (`_get_rrf_params`); contract tags don't change weights.

**Diversity rerank**: unchanged.

**Acceptance criteria:**

- [ ] `ComposeRequest(contract_path=<path>)` loads the contract and uses its `domain_tags` as BM25 input.
- [ ] `ComposeRequest(contract_tags=[...])` bypasses contract loading (useful for tests).
- [ ] Neither field set → falls back to existing rule-based keyword extraction (back-compat).
- [ ] Telemetry records the BM25 input source (`contract` vs `rule-extracted`).

### Step 2.5 — `/compose` HTTP API: accept contract_path

**Modify** `src/skillsmith/api/compose_router.py`.

Both `/compose` and `/compose/text` accept `contract_path` in the request body. If provided, the contract is loaded and validated; on validation failure, return 400 with structured error.

Add a new endpoint:

```python
POST /compose/from-contract
body: {"contract_path": "/abs/path/to/contract.md"}
→ same response as /compose, but task and phase are extracted from contract
```

This is the endpoint the (Phase 3) hook will call.

**Acceptance criteria:**

- [ ] `POST /compose` with `contract_path` works end to end.
- [ ] `POST /compose/from-contract` reads phase + tags + builds task from contract body.
- [ ] Invalid contract path returns 400 with `{"error": "contract_malformed", "issues": [...]}`.
- [ ] Existing callers without `contract_path` continue to work unchanged.

### Step 2.6 — `skillsmith compose --contract <path>` CLI

Add a new top-level subcommand `compose` (not under `install/`; this is a runtime command that calls the running service).

**Create** `src/skillsmith/install/subcommands/compose.py` (despite the name; this matches existing pattern of "everything goes through install dispatcher").

```
skillsmith compose --contract <path> [--inject]
```

- Without `--inject`: prints the composed output to stdout.
- With `--inject`: prints the output in the form a Phase 3 hook expects (prefixed with `[skillsmith]` marker, intended for stdin/stdout to harness).

Internally posts to `http://localhost:47950/compose/from-contract`.

**Acceptance criteria:**

- [ ] `skillsmith compose --contract <path>` returns the composed text.
- [ ] `--inject` formatting matches what hooks consume (verify in Phase 3).
- [ ] Service unreachable → exit non-zero with a clear message; no stack trace.

### Step 2.7 — Telemetry: record contract-driven retrieval

**Modify** `src/skillsmith/storage/vector_store.py` `CompositionTrace` dataclass.

Add fields:

```python
contract_path: str | None = None
contract_tags: list[str] = field(default_factory=list)
bm25_source: str = "rule-extracted"  # "rule-extracted" | "contract" | "union"
```

Update `ComposeOrchestrator.compose()` to populate these when a contract is involved.

**Acceptance criteria:**

- [ ] Every retrieval that loaded a contract records `contract_path` and `contract_tags`.
- [ ] `bm25_source` accurately reflects which path the BM25 query came from.

## Tests to add

`tests/test_contracts.py`:

- `test_parse_contract_minimal_valid` — only required fields
- `test_parse_contract_full_fields` — round-trip all optional fields
- `test_parse_contract_missing_frontmatter` — raises ContractMalformed
- `test_parse_contract_empty_domain_tags` — raises ContractMalformed
- `test_validate_contract_phase_mismatch` — file says phase=build, lock says phase=design → issue
- `test_validate_contract_related_contracts_missing` — referenced file doesn't exist → issue
- `test_list_contracts_for_phase_mtime_order` — newest first
- `test_latest_contract_no_phase_filter` — returns most recent regardless of phase

`tests/test_retrieval_with_contract.py`:

- `test_retrieval_uses_contract_tags_as_bm25` — assert BM25 leg got the tags
- `test_retrieval_falls_back_to_rules_when_no_contract` — back-compat
- `test_retrieval_union_when_env_var_set` — `SKILLSMITH_UNION_KEYWORDS=1`
- `test_compose_from_contract_endpoint_404_on_bad_path` — clean error
- `test_compose_from_contract_records_telemetry` — `bm25_source: "contract"`

`tests/test_customize_workflow_schema.py` (extends Phase 1 tests):

- `test_validate_workflow_requires_contract_template` — reject if missing
- `test_validate_workflow_requires_exit_gates` — reject if missing (already in Phase 1; reinforced here)
- `test_workflow_schema_accepts_phase2_minimal_gates` — only deterministic gates → valid

## Phase 2 integration test

Test scenario:

1. With Phase 1 complete, run `skillsmith profile current`. Confirm a profile is active.
2. Manually write a contract to `.skillsmith/contracts/build/test-task.md` with:
   - phase: build
   - task_slug: test-task
   - domain_tags: ["NestJS", "JWT"]
   - body: "Add JWT auth middleware"
3. Run `skillsmith contract validate .skillsmith/contracts/build/test-task.md`. Assert exit 0.
4. Set `.skillsmith/phase` to `build` (file write).
5. Run `skillsmith compose --contract .skillsmith/contracts/build/test-task.md`.
6. Assert: output is non-empty and contains fragments matching NestJS/JWT-tagged skills from the corpus.
7. Inspect telemetry (last `composition_traces` row). Assert: `contract_path` matches, `contract_tags == ["NestJS", "JWT"]`, `bm25_source == "contract"`.
8. Modify the contract to remove `NestJS`. Run compose again. Assert: results shift away from NestJS skills.
9. Run `skillsmith customize validate sdd-spec-and-scoping --profile default`. Assert: passes with the new schema.
10. Edit the local copy to remove `contract_template`. Run validate again. Assert: fails with a clear error.

If all 10 steps pass, Phase 2 is complete.

## Known gotchas

- **`python-frontmatter`** may not be in deps. Add to `pyproject.toml` `[project] dependencies` if missing. If you can't add deps, write a minimal YAML-frontmatter parser inline (~30 lines).
- **The existing `_packs/sdd/*.yaml` files have rich `raw_prose`.** Don't lose content when retagging — only add fields at the top level, leave `raw_prose` intact.
- **`sdd-build.yaml` doesn't exist** — you need to create it. Use `sdd-design-and-planning.yaml` as a template for shape and write build-phase-appropriate prose. Alternatively, defer the build workflow skill to Phase 4 if it's holding things up.
- **Bm25 query length matters.** DuckDB FTS may have token limits. If contract has dozens of tags, truncate or downweight. Phase 2 spec assumes <20 tags is normal; flag if real-world contracts blow past that.
- **The `compose` subcommand name** may collide with existing patterns. Check `_SUBCOMMANDS` in `install/__main__.py` for conflicts.
