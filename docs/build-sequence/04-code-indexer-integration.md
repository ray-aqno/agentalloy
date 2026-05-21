# Phase 4: Code-Indexer Integration

**Prerequisites:** Phases 1–3 complete. Code-Indexer service runs locally on `:8003` (or configured equivalent).

**Goal:** The active workflow skill instructs the paid LLM to call both
Skillsmith AND Code-Indexer after writing a contract, using the contract's
`scope.touches` as the code-search scope. No new artifact, no
orchestrator — the contract is shared input read independently by each
tool's CLI. After this phase, a single contract drives both
domain-skill injection AND existing-code-pattern surfacing.

**Done means:** all acceptance criteria pass AND the integration test
demonstrates a real task flow where both tools contribute context to the
paid LLM in the same turn.

## Files to modify

| Path | What changes |
|---|---|
| `src/skillsmith/_packs/sdd/sdd-design-and-planning.yaml` | Add code-indexer invocation prose to `raw_prose` |
| `src/skillsmith/_packs/sdd/sdd-build.yaml` | Same (most relevant phase for code-indexer) |
| `src/skillsmith/_packs/sdd/sdd-verify-and-review.yaml` | Same — code-indexer useful during qa for similar-pattern lookup |
| `src/skillsmith/install/subcommands/wire_harness.py` | When wiring, detect if code-indexer is reachable; bump its presence into `~/.skillsmith/state.json` |
| `src/skillsmith/contracts.py` | Add `code_indexer_query_params()` helper |
| `tools/skillsmith-signal.sh` | Optional: when `watch-contract` fires, also call code-indexer if reachable |

## Files to create

| Path | Purpose |
|---|---|
| `docs/code-indexer-integration.md` | User-facing doc explaining how the two tools compose |
| `tests/test_code_indexer_integration.py` | Verifies contract → code-indexer query construction |

## Step-by-step

### Step 4.1 — Detect Code-Indexer presence during wire

**Modify** `src/skillsmith/install/subcommands/wire_harness.py`.

After wiring the harness, probe `http://127.0.0.1:8003/health`:

- If reachable: write `{"code_indexer": {"reachable": true, "url": "http://127.0.0.1:8003", "last_health_at": <ts>}}` to `~/.skillsmith/state.json`.
- If not: write `{"code_indexer": {"reachable": false}}` and print:
  ```
  [info] code-indexer not detected on :8003. Workflow skills will still
  instruct usage; install via https://github.com/.../code-indexer to enable.
  ```

This presence flag is what workflow skills (and the `compose` output)
condition on when emitting code-indexer-related prose.

**Acceptance criteria:**

- [ ] `state.json` is created/updated with code-indexer presence info.
- [ ] Wire doesn't fail when code-indexer is absent — it's optional.
- [ ] Re-running wire updates the timestamp.

### Step 4.2 — Add `code_indexer_query_params` to contracts

**Modify** `src/skillsmith/contracts.py`.

Add:

```python
@dataclass(frozen=True)
class CodeIndexerQuery:
    repo: str                   # derived from git remote (e.g. "nrmeyers__skillsmith")
    semantic_q: str             # task title or first sentence of body
    lexical_q: str | None       # joined domain_tags
    path_globs: list[str]       # from scope.touches; empty = whole repo

def code_indexer_query_params(contract: Contract, project_root: Path) -> CodeIndexerQuery:
    """Build the parameter set a workflow skill / hook can hand to code-indexer.

    Resolves the repo slug from `git remote get-url origin` using the same
    transformation as the existing harness templates.
    """
```

The workflow skill prose tells the paid LLM the URL/params shape, but
this helper lets a hook construct the URL deterministically for the
optional auto-call path.

**Acceptance criteria:**

- [ ] `code_indexer_query_params` produces a valid query for a representative contract.
- [ ] Handles non-GitHub remotes by falling back to the project directory name.
- [ ] Empty `scope.touches` results in `path_globs: []` (whole-repo search).

### Step 4.3 — Workflow skill prose updates

For each of `sdd-design-and-planning.yaml`, `sdd-build.yaml`, `sdd-verify-and-review.yaml`, add a section to `raw_prose` along these lines:

```markdown
## Working alongside Code-Indexer

After writing a task contract at `.skillsmith/contracts/<phase>/<slug>.md`,
two tools should inform your next action:

1. **Skillsmith** — domain skill fragments based on the contract's
   `domain_tags`. These are usually injected automatically by the
   PostToolUse hook; if not, run:
       skillsmith compose --contract .skillsmith/contracts/<phase>/<slug>.md

2. **Code-Indexer** (if running) — existing code patterns in the
   `scope.touches` paths. This surfaces what already exists so you don't
   reimplement or contradict existing patterns. Run:
       curl -s "http://127.0.0.1:8003/search/semantic?q=<task title>&repo=<repo-slug>&top_k=5"
       curl -s "http://127.0.0.1:8003/search/lexical?q=<domain_tags joined>&repo=<repo-slug>&top_k=5"
       # Constrain to scope.touches with the path-filter parameter (see code-indexer docs)

Use Skillsmith for "what patterns should I follow" and Code-Indexer for
"what patterns are already in this repo." If they conflict, Code-Indexer
is the ground truth for this codebase; Skillsmith is industry best
practice. Reconcile in the contract's `scope.avoids` or
`success_criteria` before writing code.
```

**Important — conditional emission**: the prose above includes
code-indexer instructions even when code-indexer isn't installed. The
LLM may try and get a connection error. Two options:

a. **Always include the prose.** Cheap; the LLM hits a connection error
   and notes it. Workable but ugly.
b. **Conditional inclusion.** When the workflow skill is being ingested
   into the datastore, check `state.json` `code_indexer.reachable` and
   strip the code-indexer section if false. Cleaner UX, more complex.

**Recommendation:** start with (a) — simpler, easier to debug. Move to
(b) in a follow-up if users complain.

**Acceptance criteria:**

- [ ] All three target workflow skills have the new section.
- [ ] `customize validate` accepts the updated prose.
- [ ] Existing `raw_prose` content is preserved.
- [ ] The section is consistent across the three workflow skills.

### Step 4.4 — Auto-call code-indexer from PostToolUse hook (optional)

**Modify** `tools/skillsmith-signal.sh`.

In the `PostToolUse` branch, after `skillsmith signal watch-contract` (which fires Skillsmith retrieval), optionally call code-indexer too:

```bash
PostToolUse)
    TOOL="${SKILLSMITH_TOOL_NAME:-}"
    PATH_ARG="${SKILLSMITH_TOOL_PATH:-}"
    if [[ "$TOOL" =~ ^(Edit|Write|MultiEdit)$ ]] \
       && [[ "$PATH_ARG" == *".skillsmith/contracts/"* ]]; then

        # Skillsmith retrieval
        skillsmith signal watch-contract --path "$PATH_ARG" 2>/dev/null || true

        # Code-indexer retrieval (optional, gated by reachability)
        if curl -sf --max-time 1 "http://127.0.0.1:8003/health" >/dev/null 2>&1; then
            skillsmith signal code-indexer-from-contract --path "$PATH_ARG" 2>/dev/null || true
        fi
    fi
    ;;
```

Add `skillsmith signal code-indexer-from-contract` subcommand that:

1. Parses the contract.
2. Builds the query params via `code_indexer_query_params`.
3. Issues 2–3 curl calls to code-indexer (semantic, lexical, optional symbol).
4. Emits the consolidated results prefixed with `[code-indexer]`.

**Acceptance criteria:**

- [ ] Hook calls code-indexer only when reachable.
- [ ] `code-indexer-from-contract` exits 0 even when code-indexer returns errors.
- [ ] Output is interleaved with skillsmith output cleanly (skillsmith first, then code-indexer).

### Step 4.5 — Document the integration

**Create** `docs/code-indexer-integration.md`.

Audience: end users who want to understand the two-tool composition.

Sections:

- What each tool does (one-paragraph summary each)
- The contract as shared input (with example)
- The flow on a single turn (writing the contract → both tools fire → both bodies of context land in the LLM's next turn)
- Conflict resolution (when the tools disagree, code-indexer wins on facts, skillsmith wins on patterns)
- Disabling one or the other (env vars, unwire commands)
- Diagnostics (`skillsmith signal check`, code-indexer's `/health`)

This doc is what users read when they install both tools and want to understand what's happening behind the scenes.

**Acceptance criteria:**

- [ ] Doc reads top-to-bottom for someone with both tools freshly installed.
- [ ] Includes one fully worked example (a real task → contract → both tool outputs).
- [ ] Linked from the README.

## Tests to add

`tests/test_code_indexer_integration.py`:

- `test_query_params_from_full_contract` — all fields → expected query
- `test_query_params_empty_scope_touches_whole_repo` — scope.touches=[] → no path filter
- `test_query_params_handles_non_github_remote` — gitlab.com URL → falls back to dir name
- `test_state_json_records_code_indexer_presence` — wire writes state.json
- `test_hook_skips_code_indexer_when_unreachable` — health check fails → no curl calls

## Phase 4 integration test

**Goal:** verify a real task flow where both tools contribute context.

Setup: Phases 1–3 complete, code-indexer running on :8003 with the
current repo indexed.

Test scenario:

1. Start a fresh Claude Code session in the repo.
2. Set phase to `build`.
3. Prompt Claude: "Add a retry helper for HTTP calls in the storage layer."
4. Claude should write `.skillsmith/contracts/build/http-retry-helper.md` with `domain_tags: ["http", "retry", "exponential backoff"]` and `scope.touches: ["src/skillsmith/storage/**"]`.
5. PostToolUse fires:
   - `skillsmith signal watch-contract` → loads contract → `compose --contract` → emits retry/HTTP-tagged domain fragments.
   - `skillsmith signal code-indexer-from-contract` → queries code-indexer with `q="retry helper for HTTP"`, `repo=nrmeyers__skillsmith`, path-filter `src/skillsmith/storage/**` → emits existing HTTP helpers from the repo.
6. Inspect the next prompt's context. Assert both `[skillsmith]` and `[code-indexer]` blocks are present.
7. Claude should then make a decision informed by both: e.g., "I see there's already an existing `_retry_with_backoff` in storage/vector_store.py (code-indexer); per the skillsmith retry skill, I'll reuse it rather than implement a new one."
8. Inspect telemetry. Assert: 1 `contract_retrieval` (skillsmith), at least one code-indexer call logged (if code-indexer logs centrally; otherwise verify via skillsmith's emitted output).

If 1–8 pass, Phase 4 is complete.

## Known gotchas

- **Code-indexer URL hardcoding.** The hook script hardcodes `:8003`. Make this configurable via `SKILLSMITH_CODE_INDEXER_URL` env var (defaulted in `Settings`).
- **Repo slug derivation** must match what code-indexer uses internally. Check code-indexer's slug algorithm and align Skillsmith's to it (or query code-indexer's `/health` for `indexed_repos` and pick the best match).
- **Conditional prose stripping (option b above)** is appealing but requires re-ingesting workflow skills whenever code-indexer presence changes. Option (a) is simpler — the LLM handles missing services well enough.
- **Two big context injections per turn** when a contract is written: domain fragments AND code-indexer results. Watch context budget. If it gets noisy, reduce code-indexer `top_k` from 5 to 3.
- **Path-filter support in code-indexer.** Verify the running service supports a path-filter or scope param on `/search/semantic`. If not, scope.touches is informational only and code-indexer searches the whole repo. Either way it works; just less precise.
