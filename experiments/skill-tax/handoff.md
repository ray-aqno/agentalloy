# skill-tax POC — Handoff

You're picking up the skill-tax POC inside `experiments/skill-tax/`. The work has been scoped in a prior chat session; everything you need is in three reference docs in this directory:

- `workflow-phase-retrieval-pilot-spec.md` (v2.3) — the experimental design. Read this first, fully, before doing anything else.
- `skillsmith-authoring-reference.md` — schema, R-rules, fragment types, QA gate behavior.
- `skillsmith-model-selection.md` — which model authors what.

## What this POC tests

Whether the skillsmith fragment-typed retrieval architecture supports Tier 2 (Qwen3-Coder-30B-A3B-Instruct, Unsloth GGUF Q4_K_S) deterministic execution, holding authoring quality constant by using only gold-standard skills. The pilot spec details the full hypothesis structure (H1 + sub-claims C1–C4), trial design, decision rules, effort estimates, and the locked Tier 2 runtime configuration (spec §2.4).

## Where things stand

_Updated 2026-05-04_

- Spec is finalized at v2.3.
- No skills authored yet.
- No harness built.
- No tasks specified.
- **Both skill data stores are empty and schema-verified (LadybugDB and DuckDB).** Tables exist and are current. `composition_traces` (561 rows from prior eval runs) and `pilot_trials` tables are present in `experiments/skill-tax/skills.duck`. The active corpus stores at `~/.local/share/skillsmith/corpus/` have 0 fragments — clean slate confirmed.
- A pre-POC corpus (153 skills, 1658 fragments) has been archived to `~/.local/share/skillsmith/archive/pre-poc-2026-04-27/`. It does not meet the pilot quality bar (only 35/153 had all 6 fragment types; R3 verification severely underrepresented). Do not use it.
- DuckDB telemetry stack is operational. `pilot_trials` schema migration is at `experiments/skill-tax/migrations/001_pilot_trials.sql` — apply before trial execution.
- **R1 sourcing now has a tiered strategy.** See `fixtures/upstream/registry.yaml` and `fixtures/upstream/curated/` — use these before doing any web research for skill authoring. Details below.

## Pre-flight: confirm the clean-slate state is workable

Before authoring any skill, verify the following — the cleared stores mean some assumptions don't hold automatically anymore:

1. **Schema state.** ✅ _Verified 2026-05-04._ Tables are present and current in both stores. `composition_traces`, `pilot_trials`, `fragment_embeddings`, `prompt_loads` all exist. No migrations needed before authoring.

2. **Pack registry / tier metadata.** Verify pack registry state before authoring — this was not checked in the 2026-05-04 session.

3. **Existing webhook-patterns skill.** Since the stores are cleared, the canonical `webhook-patterns` skill is no longer ingested — only the YAML on disk at `src/skillsmith/_packs/webhooks/webhook-patterns.yaml` remains. The pilot still uses the YAML directly (skills are loaded from file in the harness, per spec), so this is fine. But if any tooling assumes the skill is queryable from the store, that tooling will break until it's re-ingested.

4. **Embeddings / retrieval indexes.** ✅ _Verified 2026-05-04._ `fragment_embeddings` is empty (0 rows). Pilot uses manual fragment selection (spec §5) so this is not blocking.

5. **Re-ingestion strategy for the four pilot skills.** Decide upfront whether the four authored skills will be:
   - **(a) Loaded from YAML at trial time only** — no ingestion needed; pilot is fully file-based. Simplest, cleanest, recommended.
   - **(b) Re-ingested into the cleared stores after authoring** — required if the pilot wants to test the actual ingestion path or if downstream tooling needs DB-resident skills.

   The spec assumes (a). Confirm this before authoring; if (b) is needed, it adds an ingestion step per skill.

If any of the above checks turn up something unexpected, surface it rather than work around it. Cleared-store edge cases are exactly the kind of thing that produces subtle pilot contamination.

## First milestone — gold-standard skills

This milestone is bounded. Don't start the harness, tasks, or trial work yet. Skills first; everything downstream depends on them being unambiguously gold standard.

### 1. Augment `webhook-patterns.yaml` with an explicit `guardrail` fragment

The existing `src/skillsmith/_packs/webhooks/webhook-patterns.yaml` has 8 fragments but no `guardrail`. Candidate guardrail content already exists inline in the execution fragments (e.g., "never use `===` for HMAC comparison") — promote it into a dedicated guardrail fragment.

- Update `change_summary` honestly to reflect the augmentation, not claim "initial authoring."
- Bump version per the authoring reference's versioning rules.
- Validate against full schema (R-rules, contiguity, word counts).

**Open question for you to resolve:** edit the canonical pack file in place, or fork into `experiments/skill-tax/skills/` as a pilot-local copy? Default to pilot-local fork unless you have a strong reason to touch production-pack content. If you fork, document the divergence so the pilot's webhook skill doesn't drift from canonical silently.

### 2. Author three new skills via research LLM (per `skillsmith-model-selection.md`)

- `jwt-validation-patterns` (protocol tier)
- `fastapi-middleware-patterns` (framework tier)
- `python-async-patterns` (language tier)

**R1 sourcing — use the tiered registry before doing any web research.** As of 2026-05-04 the following sources are available:

| Skill | Tier | Source |
|---|---|---|
| `python-async-patterns` | Tier-3 | `fixtures/upstream/curated/python.yaml` (once generated) → `docs.python.org/3/library/asyncio.html`, key PEPs |
| `fastapi-middleware-patterns` | Tier-3 | `fixtures/upstream/curated/python.yaml` + `fallback_root: https://fastapi.tiangolo.com/` (no llms.txt) |
| `jwt-validation-patterns` | Tier-3 | OWASP JWT cheat sheet, PyJWT docs, RFC 7519. No llms.txt for any of these — use web fetch. |

Check `fixtures/upstream/registry.yaml` and `fixtures/upstream/curated/` before fetching. If `python.yaml` hasn't been generated yet, run the Sonnet batch (see `fixtures/upstream/curated/_prompt-template.md` + `_targets.yaml`).

Per-skill research is mandatory: research JWT before authoring JWT; research FastAPI before authoring FastAPI middleware; research async before authoring async patterns. Don't bulk-research and then author from memory. Date-stamp per R5 with the actual research date.

### 3. Quality bar (non-negotiable)

Each skill must:

- Pass full schema validation (R-rules, fragment word counts, contiguity, tag policy)
- Include all six fragment types: `rationale + setup + execution + verification + example + guardrail` — minimum one of each
- **Include an explicit `guardrail` fragment** (this is non-negotiable for the pilot — without it the pilot's Arm B vs Arm C comparison breaks)
- Reach final QA gate verdict of `approve` (revise → approve through normal iteration is fine; bounce_budget exceeded → re-author from a different angle)
- Cite primary sources per R1
- Date-stamp per R5

**If QA gate can't produce gold-standard content for a given skill across two distinct authoring attempts (different prompts or sessions), pause and surface it rather than lower the bar.** Better to test 3-skill composition with 3 gold-standard skills than 4-skill with one borderline skill.

### 4. Iteration history goes off-repo

Authoring drafts, QA verdicts, and intermediate artifacts go in `~/work/skill-authoring-runs/<skill_name>/` (or equivalent local working directory).

Only `final-approved.yaml` for each skill lands in `experiments/skill-tax/skills/`.

This separation keeps the pilot's reproducibility artifact clean while preserving the iteration history as evidence the authoring process was rigorous.

### 5. Maintain `experiments/skill-tax/skills/AUTHORING_LOG.md`

One entry per skill, capturing:

- Research LLM model used
- Research sources consulted (per-skill, with dates)
- Number of QA gate iterations
- Final verdict
- Human reviewer name (if applicable) and sign-off date
- Any notable issues, divergences, or decisions

This log is what defends "gold standard" if the pilot fails and someone asks whether authoring quality was the bottleneck.

## Order of operations

1. Read all three reference docs fully.
2. **Run pre-flight checks** (the section above): confirm schema state, pack registry, re-ingestion strategy. Do not skip — cleared stores mean assumptions need verification before authoring starts.
3. Decide canonical-vs-fork on the webhook skill augmentation.
4. Augment webhook skill first (smallest scope, validates the workflow end-to-end against current schema state).
5. Author the three new skills sequentially. Per-skill: web research → draft → QA gate → revise loop → final-approved.
6. Maintain `AUTHORING_LOG.md` as you go, not after.
7. Surface the milestone as complete once all four skills are in `experiments/skill-tax/skills/` with the log fully populated.

## What's next (do NOT start until milestone 1 is signed off)

- Task specification (6 tasks per spec §4.2): T1, T2, T3a, T3b, T4, T5
- FastAPI app skeleton fixtures
- Trial harness with arm-construction logic
- `pilot_trials` schema migration
- Token-budget measurement after authoring (record actual prompt sizes per arm; the 32K context window with 256K native model headroom should leave ample margin, but real measurements lock the §5.3 estimates)
- Trial execution
- Verification + root-cause tagging
- Aggregate + writeup

These are separate milestones with their own scoping. Don't anticipate them while authoring skills.

## Things to flag back rather than decide unilaterally

- Schema validation failures that don't have a clear fix path
- QA gate behavior that contradicts the authoring reference
- Composition concerns surfacing during authoring (e.g., two skills overlapping in ways that won't compose cleanly in T3a/T3b)
- Token-budget concerns if any single skill is approaching the upper word-count limits
- Anything in the spec that becomes ambiguous when you start implementing against it

The spec was written before any of this was built. It will have gaps. Surfacing them is more valuable than papering over them.
