# Unmerged Branches — Status Summary

## Merged (done)
- **ladybug-migration** → merged to main as PR #62. No further action needed.

## Cleaned up (merged or trivial)
- **fix/deprecated-warning-manual-harness** → merged as PR #51. Deleted remote + local branch.
- **bench/benchmark-evaluation** → trivial CI re-trigger. Deleted.
- **feature/container-kuzu-lock-resolution-design** → just formatting. Deleted.
- **feat/deprecated-skill-tests** → merged into main. Deleted remote branch.
- **chore/duckdb-min-version-upgrade** → merged as PR #63. Deleted remote branch.

---

## 1. fix/deprecated-warning-manual-harness (local + remote)

**Status:** Has a PR on GitHub. Not yet reviewed or merged.

### Commits (in order)

#### `b32768c` — fix: container readiness tests and ruff cleanup
- Fixes container readiness tests
- Ruff formatting cleanup

#### `b988b40` — fix: address Copilot review findings
- Addresses review comments from Copilot

#### `b988b40` → `8edea14` — chore: re-trigger CI

#### `02d9c0f` — fix: use per-turn hooks for Claude Code on native install (#50)
- **Intent:** Claude Code on native install was incorrectly going through proxy wiring
  (writes `~/.agentalloy/claude-code-env.sh`) instead of the per-turn hook method
  (writes `~/.claude/claude-code-hooks.json`).
- **Change:** Set `legacy=True` for Claude Code on native deployment. The old code
  only set `legacy` for `PROXY_UNABLE_HARNESSES` but Claude Code also needs it since
  the hook method is the correct approach on native (proxy wiring is only for container mode).
- **File:** `src/agentalloy/install/subcommands/simple_setup.py`

#### `a18ed04` / `8edea14` — fix: suppress deprecated skill warning during install; gate upstream prompt on harness (#51)
- **Intent:** Two fixes in one commit:
  1. Remove the `print("WARNING: skipping deprecated skill...", file=sys.stderr)` from
     `_ingest_yaml()` in `install_pack.py`. The outcome is already tracked in the result
     dict, so the stderr output is noise during install.
  2. Gate `_prompt_upstream()` behind `cfg.harness not in ("manual", "claude-code")`.
     Manual harness doesn't need proxy wiring; Claude Code uses per-turn hooks instead.
     Without this gate, the setup script would incorrectly prompt for an upstream LLM
     when the harness is "manual" or "claude-code".
- **Files:** `src/agentalloy/install/subcommands/install_pack.py`,
  `src/agentalloy/install/subcommands/simple_setup.py`

#### `d592422` — chore: re-trigger CI

#### `1f3cf38` — fix: resolve test cycle findings (Issues 1-4)
- **Intent:** Fix 4 issues discovered during the test cycle:
  - **Issues 1-2 (Native):** Ollama SSH key path + FTS index rebuild
    - Add auto-copy of SSH key to `~/.ollama/id_ed25519` in `pull_models.py`
      (Ollama 0.20.3 looks for the key there, not at `~/.ssh/id_ed25519`)
    - Fix DuckDB FTS stopwords corruption in `vector_store.py`
  - **Issues 3-4 (Container):** Empty packs + LadybugDB lock conflict
    - Replace empty-packs skip with `install-packs --non-interactive --no-restart`
    - Move uvicorn start from before pack install to after bootstrap complete
    - Fix grep -c syntax issue in per-pack loop
    - Update docstring to reflect new 9-step bootstrap sequence
  - Add 22 new tests (6 integration + 9 edge case + 3 readiness + 4 backward compat)
  - Update 3 existing test expectations for new script ordering
- **Files:** `src/agentalloy/install/subcommands/pull_models.py`,
  `src/agentalloy/storage/vector_store.py`, `src/agentalloy/reembed/cli.py`,
  `tests/test_container_edge_cases.py`, `tests/test_ollama_ssh_key.py`,
  `tests/test_vector_store.py`, plus spec/design/plan/test docs

#### `b32768c` → `b988b40` — benchmark: replace flat injection with MCP skill dictionary pattern
- Refactors evaluation framework
- **Files:** `eval/benchmark.py`, `eval/layers/cross_model.py`, `eval/run_poc.py`,
  `eval/tasks.py`

### Additional changes on this branch
- `docs/plan/test-cycle-fixes.md`, `docs/specs/test-cycle-fixes.md`,
  `docs/design/test-cycle-fixes.md`, `docs/tests/test-cycle-fixes.md` — SDD docs
  for the test cycle fixes (should probably be gitignored)
- `README.md`, `BENCHMARKS.md`, `docs/operator.md` — documentation updates

### What's still relevant
- **Core fixes (definitely keep):** deprecated skill warning removal, upstream LLM
  prompt gating, Claude Code legacy flag fix, Ollama SSH key copy, install_packs.py
  stat() try/except
- **Test cycle fixes:** Ollama SSH key, install-packs non-interactive fix, bootstrap
  ordering, vector_store.py FTS fallback, reembed warning message update, 22 new tests
- **DuckDB FTS fallback in vector_store.py:** Adds Phase 2 catalog reset fallback for
  checkpoint-based retries. This was written for DuckDB 1.5.2 but the project now
  requires 1.5.3 which fixes the FTS bug. May not be needed — should verify.
- **Benchmark/eval changes:** MCP skill dictionary pattern, cross-model evaluation
  refactoring. Separate concern from the core fixes.
- **SDD docs:** Should probably be gitignored.

---

## 2. bench/benchmark-evaluation (local + remote)

**Status:** Single commit, trivial.

#### `d592422` — chore: re-trigger CI
- Just a CI re-trigger. No code changes.
- **Can likely be deleted.**

---

## 3. feat/deprecated-skill-tests (remote only)

**Status:** Single commit, remote only.

#### `test: add deprecated skill skipping tests for install_pack`
- Adds tests for deprecated skill skipping in `install_pack.py`.
- Small, focused test branch.
- **Could be squashed into the deprecated-warning branch or merged separately.**

---

## 4. feature/container-kuzu-lock-resolution-design (remote only)

**Status:** Single commit, remote only.

#### `fix: format test_container_edge_cases.py with ruff`
- Just a formatting commit. No code changes.
- **Can likely be deleted.**

---
