# Skill Authoring Methodology

> Operational playbook for authoring a new skill, validating it, and getting it into the production data stores. Integrates the schema/rules reference (`docs/skillsmith-authoring-reference.md`) with pilot-derived guidance (`experiments/skill-tax/reviews/_POC_FINAL.md`) and the actual storage pipeline. This document is the front-to-back walkthrough.

> **Scope.** Covers domain skills end-to-end. System skills (`sys-*`) follow the same flow with the additional constraints in §1.3 of `skillsmith-authoring-reference.md`. Workflow skills add the W1 contract rule.

---

## Quick reference — the full lifecycle

```
[1] DESIGN          → SKILL.md draft + scope decision
[2] AUTHOR          → pending-qa/<skill_id>.yaml (LLM-assisted or hand-written)
[3] QA GATE         → deterministic lint → dedup → critic LLM
                       └─→ pending-review / pending-revision / rejected / needs-human
[4] INGEST          → LadybugDB (graph: Skill / SkillVersion / Fragment nodes)
[5] EMBED           → DuckDB (fragment vectors via reembed pass)
[6] VERIFY          → live retrieval test (BM25 + vector hits, applicability)
[7] PROMOTE         → mark pack version released; update inventory
[8] MAINTAIN        → versioning on changes; deprecation when retired
```

Each phase has its own §. Read them in order on a first pass; reference individually after.

---

## Phase 1 — Design (before writing any YAML)

**Goal of this phase:** decide whether the skill should exist at all, what cognitive shape it serves, and what tier it belongs to. Skipping design is the most common cause of skills that lint clean but fail in retrieval or production.

### 1.1 Decide the skill's reason to exist

Ask in order:

1. **Does the underlying knowledge have non-obvious load-bearing detail?** If the model's training-data prior already produces correct output without external context, a skill won't move the needle. Pilot evidence: T1 (Stripe webhook from blank seed) at 30B-A3B Coder scale passes 100% via SDK shortcut whether fragments are present or not. The model didn't need the skill. Don't author skills for tasks the target tier handles unaided.
2. **Does it cover a procedure, contract, or guardrail that breaks when violated?** Skills earn their keep when (a) the right pattern isn't dominant in training data (org-specific, post-cutoff, regulated-domain) or (b) plausible-but-wrong patterns are abundant in training data and the skill names them as anti-patterns.
3. **Is the scope narrow enough to be a single skill, or wide enough that it should be a pack?** A skill answers "how do I do X correctly in this codebase / domain" — single coherent surface. A pack groups skills around a shared toolset (`webhooks`, `nestjs`, `airflow`). If you can't write a one-sentence reason-to-exist, the scope is wrong.

### 1.2 Pick the cognitive shape

Pilot M5–M8 surfaced four cognitive shapes (build-domain). Different shapes have different parameter floors and different fragment-composition needs:

| Cognitive shape | Definition | Fragment emphasis |
|-----------------|------------|---------------------|
| **Net-new bounded** | Build a new file/module from a near-empty seed | execution + setup heavy; example shows full handler shape |
| **Targeted local refactor** | One-line or one-block change to existing code | guardrail + anti_pattern + execution; rationale + example are *load-bearing* (pilot C1 refutation evidence) |
| **Multi-skill composition** | Wire two or more skills together (middleware + handler + auth + DB) | requires code-index retrieval to work at all; skill content alone is insufficient |
| **Inverted-criterion decline** | Task should be declined because scope exceeds fragments | rationale + decline-shape guardrail |

If your skill primarily serves one shape, design fragments for that shape. A webhook-domain skill that supports both "build new receiver" and "refactor existing receiver" needs both rationale (for net-new) AND anti-patterns (for refactor — preserve other behavior).

For non-build domains (interview, architecture, devops), shape taxonomy is its own pilot — the build-domain shapes don't transfer directly, but the *methodology* of asking "what cognitive shape does this serve" does.

### 1.3 Pick the skill class and tier

| Class | When to use | Tier resolution |
|-------|-------------|------------------|
| `domain` | Knowledge unit specific to a tool, framework, protocol, or domain | From sibling `pack.yaml`; one of `protocol`, `framework`, `language`, etc. |
| `system` | Always-on governance, operational discipline, safety guardrails | `skill_id` MUST start with `sys-`; `domain_tags` MUST be `[]` |
| `workflow` | Procedural composition skill (intake → spec → design → build → ...) | Includes W1 workflow-position marker |

Tier ladder for domain skills (per `docs/skillsmith-pack-inventory.md`): `protocol` (e.g. webhook signature schemes) > `framework` (e.g. FastAPI middleware) > `language` (e.g. Python async patterns) > `convention` > `cross-cutting`.

If you can't decide, the pack manifest's `tier` resolves it for you. If the pack doesn't exist yet, see `docs/PACK-AUTHORING.md` first — pack design precedes skill design when a new tool/domain is being introduced.

### 1.4 Source discipline — line up authoritative sources before drafting

Per R1 (`skillsmith-authoring-reference.md` §3): for fast-moving APIs (e.g. FastAPI 0.115+, Stripe SDK ≥10), fetch the canonical docs and pin the verification date in the skill content. The pilot's webhook-patterns:7 and :8 fragments include `verified 2026-05-01` markers for exactly this reason.

**Source authority hierarchy** (from `skillsmith-authoring-reference.md` §10.2):

1. Official vendor/protocol docs at the verified date
2. RFC / formal specification
3. Stable language standard library docs
4. Source code of the canonical reference implementation
5. Empirical verification (a code snippet you ran and confirmed)

NOT acceptable as primary sources: blog posts (use only as pointers to canonical), Stack Overflow answers, generic AI-generated summaries (R7 violation if not flagged).

### 1.5 Write the SKILL.md source

The source markdown is the *canonical prose* the skill is built from. Every fragment's `content` field must be a contiguous slice of the SKILL.md (whitespace-normalized) per the contiguity rule (R5.5). If you write the YAML first and the source markdown second, you'll fail dedup / contiguity checks.

Template:

```markdown
# <Canonical Name>

<one-paragraph rationale: why this skill exists, what it covers, what it doesn't>

## Setup

<imports, env vars, prerequisite installs, raw-body capture if relevant>

## <Execution section 1>

<the procedure, code, error handling — verbatim, no shortcuts>

## <Execution section 2>

<continuing the procedure>

## End-to-end example

<a complete worked example covering the case-space (R4): happy path,
failure path, edge case>

## Verification checklist

<mechanical checks; each item must be grep-able or test-runnable per R3>

## Guardrails: never do these

<anti-patterns from production experience; each one is a "bug we've seen ship">
```

**Anti-pattern fragments** (added in M7 of the pilot): if the domain has a known set of plausible-but-wrong patterns the model exhibits in production, author them as a separate `anti_pattern` fragment with the format:

```markdown
## Common bug: <name>

<observed behavior>

**Why this is wrong:** <mechanism>

**Correct approach:** see <skill_id:fragment_seq>.
```

Pair each anti-pattern with a one-line pointer back to the existing instructional fragment that shows the right way. M7 evidence: anti-pattern fragments alone don't lift functional pass at small parameter scale (model has the bug-flag, application still fails), but they do help reviewers diagnose failures and plausibly help mid-tier execution models that operate above the application threshold.

---

## Phase 2 — YAML Authoring

### 2.1 Two paths: LLM-assisted vs hand-written

**LLM-assisted (preferred for new skills):**

```bash
# Place SKILL.md drafts at skill-source/<skill_id>/SKILL.md, then:
python -m skillsmith.authoring author --pack <pack-name>
```

The driver (`src/skillsmith/authoring/driver.py`) walks `skill-source/`, runs the authoring prompt at `fixtures/skill-authoring-agent.md` against each SKILL.md, and emits `pending-qa/<skill_id>.yaml`. The authoring agent transforms prose into the structured fragment schema.

### 2.1a Model selection for the authoring agent

**Cloud (Claude) routing — see `docs/skillsmith-model-selection.md`** for the full Opus 4.7 / Sonnet 4.6 split. Summary: Opus for source-grounded drafting on `language` / `framework` / `protocol` / `store` / `domain` tiers; Sonnet for `workflow` / stable `foundation` tiers; Opus for pack design and semantic-lint diagnosis; first 2–3 packs end-to-end on Opus for calibration.

**Local-only routing (when cloud token budget is constrained).** The authoring cognitive shape is constant across pack tiers — structured-output transformation with source-fidelity discipline and judgment about granularity. What varies by tier is *training-data depth* and *whether canonical-source-fetch is required*. Recommended local routing on the operator's available slate:

| Pack tier | Local model | Training-data depth | Fetch capability | Suggested prompt directive | Notes |
|-----------|-------------|----------------------|------------------|------------------------------|-------|
| `workflow` (SDD process, code-review checklists, RFC guides) | `qwen3.6-27b@q4_k_m` | **Low** — content is organizational practice, not external API | **Not required** — source is the operator's own SKILL.md / org conventions | "Author per `docs/skillsmith-authoring-reference.md` §1–§5. Source is SKILL.md only — do NOT fetch external docs. Verification items must be auditable practices (e.g. 'reviewer checks X via Y'), not external API claims. R6 honesty: change_summary names the org-process source." | General Instruct at 27B handles process content. q4 fine because fabrication risk is low. |
| `foundation` (stable cross-cutting patterns) | `qwen3.6-27b@q4_k_m` | **Medium** — needs general engineering knowledge (debugging, error-handling philosophies, common architectures) | **Optional** — fetch only for any version-specific claims that creep in | "Author per ref. Synthesize from training data on stable patterns. If a claim involves a specific tool or version, STOP — fetch the canonical doc, quote a snippet into the verification fragment, R5 date-stamp. When uncertain, frame claims as 'pattern observation' rather than 'documented behavior.'" | Synthesis-friendly; same model class as workflow. |
| `language` (Python, TypeScript idioms) | `qwen3.6-27b@q8_k_xl` (preferred) or `qwen3-coder-30b-a3b-instruct` | **High** — language semantics, stdlib behavior, version-specific features (e.g., Python 3.12 typing) | **Recommended** — language standards evolve; date-stamp claims about minimum version | "Author per ref. For language-semantics claims, fetch the canonical doc (Python docs, TC39 spec, Rust reference) and quote verbatim snippets into verification fragment with R5 date-stamps. Every minimum-version claim is dated. Code blocks: every non-stdlib symbol gets exactly one `import` (R2)." | Higher quant preserves precision on language semantics. q8 dense general is the better default; Coder-tuning can over-bias toward code shapes when prose rationale is needed. |
| `framework` (FastAPI, NestJS, Airflow) | `qwen3-coder-30b-a3b-instruct` + **mandatory canonical-source-fetch** | **High** — current-version awareness for fast-moving APIs (FastAPI 0.115+, NestJS 10+) | **Mandatory** (R1) — fetch official docs at authoring time, quote snippets into verification fragment, R5 date-stamp | "MANDATORY: before drafting any fragment, fetch the framework's official docs at the version pinned in `pack.yaml`. Quote relevant snippets into the verification fragment with URL + date-stamp. If fetch fails, STOP and declare — do not draft from training data alone. Code blocks must be runnable on the pinned version (no deprecated APIs, no future-cutoff features)." | Code-heavy fragments; Coder model produces runnable examples. |
| `protocol` (signature schemes, JWT, OAuth) | `qwen3-coder-30b-a3b-instruct` + **mandatory canonical-source-fetch** | **High** — security-sensitive; claims must match RFC / spec exactly | **Mandatory** — RFC + vendor docs (e.g. Stripe webhook docs, RFC 7519 for JWT). Verbatim algorithm names, exact status codes. | "MANDATORY: fetch the RFC + vendor docs before drafting. Algorithm names (HS256, RS256, HMAC-SHA256), status codes (400/401/403), and header formats are quoted VERBATIM from the spec. Every verification item cites RFC section number and vendor doc URL with date-stamp. Treat any uncited security claim as a fabrication risk and refuse to emit it." | Fabrication here is a security risk. The verification fragment carries the load. |
| `store` (Postgres, Redis, ClickHouse) | `qwen3-coder-30b-a3b-instruct` + **mandatory canonical-source-fetch** | **High** — query syntax, performance characteristics, version-specific features (Postgres 16 vs 17, Redis 7 streams, etc.) | **Mandatory** — vendor docs at the version pinned in pack.yaml. Quote SQL/command snippets verbatim. | "MANDATORY: fetch vendor docs at the version pinned in `pack.yaml`. SQL/command syntax is quoted verbatim — no paraphrasing of `CREATE TABLE` constraints, index types, or transaction-isolation levels. Performance claims cite version + source. Code blocks must execute cleanly against the pinned version (test with the operator's local runtime if possible)." | SQL/query examples need to be runnable; Coder tuning helps. |
| `domain` (Stripe webhooks, AWS Lambda) | `qwen3-coder-30b-a3b-instruct` or `qwen/qwen3.6-35b-a3b` + **mandatory canonical-source-fetch** | **High** — vendor-specific API knowledge, often changes without notice (deprecations, new fields) | **Mandatory** — vendor docs at the verified date. Stripe SDK version pinning, Lambda runtime version pinning, webhook event structure. | "MANDATORY: fetch vendor docs at the verified date. Pin SDK version, Lambda runtime, webhook event schema versions in the setup fragment. Vendor APIs deprecate without notice — every behavioral claim has a date-stamp tied to the doc URL fetched. If the SDK has multiple supported call shapes, document the canonical one per the active SDK major version, and reference the migration path for the prior major." | 30B-A3B Coder matches pilot authoring conditions. 35B-A3B general is alternative if more reasoning headroom is needed and less code-tuning bias preferred. |
| `cross-cutting` (security, observability, performance) | `qwen/qwen3.6-35b-a3b` (general, high reasoning) | **High** — synthesis across tools; needs broad pretraining over the topic surface (CVE patterns, OWASP Top 10, OTLP semantic conventions) | **Recommended** — security guidance rotates (OWASP, NIST). Date-stamp recommendations. | "Author per ref. Synthesize across tools — pull canonical source per claim (OWASP Top 10, NIST guidelines, OTLP semantic conventions, CVE entries). Date-stamp every recommendation against the doc revision fetched. Skill scope is the cross-cutting concern itself, not any single tool — example fragments may cite multiple tools but the rationale generalizes." | Cross-cutting needs synthesis across tools; general-tuned with more parameters handles this better than code-tuned. |
| Pack design (judgment-heavy, low volume) | `qwen/qwen3.6-35b-a3b` | **High** — needs broad technology-landscape awareness to draw skill boundaries and identify high-leverage patterns | **Optional during design** — design is conversational and iterative; fetch when boundaries depend on specific framework constraints | "You are designing a pack, NOT drafting skills. Output a pack outline: prioritized skill list, draft skill_id for each, one-sentence reason-to-exist, recommended canonical sources for fact-grounded claims. Identify skill boundaries, high-leverage areas, and common pitfalls in the domain. Operator reviews and approves the design before any drafting begins." | Closest local match to the Opus pack-design role. Manual operator review of design output recommended. |
| Mechanical lint fixes between iterations | `qwen2.5-coder-3b-instruct-128k` | **Low** — small local edits to YAML structure (synonym swaps, missing markers, title-overlap fixes) | **Not required** — operating on the YAML, not on facts | "Address each `blocking_issue` from `<skill_id>.qa.md`. Line-level edits ONLY — do not redesign, do not re-author fragments, do not change the contiguity of `raw_prose`. Move the YAML back to `pending-qa/` and stop." | Small local edits, fast iteration. |

**The honest quality cost:** local 27B–35B models are roughly Sonnet-tier on most authoring tasks but **noticeably below Opus** on (a) source-verification (knowing when training-data recall is wrong), (b) cross-source synthesis, (c) detecting subtle R7 fabrications in own output, (d) judgment calls about skill boundaries during pack design. The pilot validated Qwen3.6-27B at the *critic* role; first-pass *drafting* on local 27B class will produce more fabrications than Opus would.

**Mitigations (non-optional for local-only authoring):**

1. **Mandatory canonical-source-fetch in the authoring prompt.** Don't trust training-data recall. The authoring prompt requires the agent to fetch the canonical doc, quote a relevant snippet into the verification fragment, and date-stamp it (R5). If the agent can't fetch, declare and escalate.
2. **Stronger Stage 3 critic.** Use `qwen3.6-27b@q4_k_m` and tune the critic prompt to be suspicious by default — flag anything that looks like training-data filler. Lower the bar for `revise` verdicts.
3. **Manual operator review of every `pending-review/` YAML before ingest.** Read the verification fragment first — if its citations don't trace to real sources, kick back to revision. The R6 change_summary trail is the audit lever.

**Mitigations (nice-to-have for high-stakes tiers):**

4. **Two-pass authoring for protocol, store, domain.** Author with `qwen3-coder-30b-a3b-instruct`, then run a self-review pass with `qwen/qwen3.6-35b-a3b` (different model, different perspective) before qa_gate. Mirrors pilot M8's self-QA finding.
5. **Local calibration scope-shift.** Replace "first 2-3 packs on Opus" with "first 2-3 packs with operator review of every fragment before commit." After calibration, the routing rule above can run with less per-skill operator time.

**Why cognitive shape is constant but training-data alignment isn't:** the agent's job at every tier is the same — transform SKILL.md into structured YAML satisfying R1–R8. What changes is the model's ability to *recognize errors in SKILL.md itself* (which depends on domain training data) and the *need for canonical-source-fetch* (which depends on whether the domain has fast-moving APIs). One general capable authoring model can author all tiers IF paired with mandatory fetch for fact-dependent tiers; specialized code-tuning helps but isn't strictly required.

**Hand-written (for surgical edits or system skills):**

Drop a file directly in `skill-source/pending-qa/<skill_id>.yaml` matching the schema in `docs/skillsmith-authoring-reference.md` §1.

### 2.2 Fragment composition — pilot-derived guidance

The pilot's evidence (M2 baseline → M8 self-QA) refines what makes a fragment set effective. Author with these in mind:

**Rationale + example are load-bearing for execution-routed queries** (refutes spec C1 prediction). Include both for any domain skill that targets cognitive shapes where the model could plausibly rewrite seed code (T4-style targeted refactors). Drop them only for the highest-tier execution arms where context budget pressure forces it.

**Procedure / execution fragments must be *runnable*.** Per R2, every non-stdlib symbol gets its `import` once. Per R3, every verification item must be mechanically checkable (grep, test, type-check). The pilot found that small models produce code that *looks like* Python but crashes uvicorn at 49% — fragment authoring's job is to remove that ambiguity, not introduce it.

**Guardrail fragments are anti-pattern listings.** Each item must be a "production-bitten" rule with a concrete failure mode. webhook-patterns:8 is the gold-standard example. Per pilot evidence, guardrail content alone does not prevent small-model rewriting (the model paraphrases the guardrail in comments while still violating it in code) — but it gives reviewers and larger models the explicit anti-pattern surface they need.

**Anti-pattern fragments (`anti_pattern` type) are surgical add-ons.** Add when production trace data shows a specific bug pattern that the existing fragments don't surface explicitly. M7 pattern: "Common bug: X. Why it's wrong: Y. Correct approach: see skill:N." Don't add anti-pattern fragments speculatively — they earn their keep by mapping to bugs you've actually observed.

**Verification fragments double as fabrication defense.** Per `skillsmith-authoring-reference.md` §6.5, verification items doubling as "this is what passes" forces the author to demonstrate their procedure mechanically, which surfaces fabricated examples (R7) at authoring time.

### 2.3 Fragment word-count discipline

Per `docs/skillsmith-authoring-reference.md` §5.2:
- Soft warn: < 80 words or > 800 words (review for split / consolidate)
- Hard fail: < 20 words or > 2000 words (fragment is malformed)

Long execution sections that legitimately exceed 800 words should be split into sequential fragments (e.g., `:3` and `:4` both `execution` type with logical breaks). Don't concatenate to "fit" the word count.

### 2.4 Fragment ordering within a skill

Sequence numbers are author-controlled. Convention (per gold-standard skills):

| Sequence | Type | Purpose |
|----------|------|---------|
| 1 | rationale | Why this skill exists |
| 2 | setup | Imports, env, prerequisites |
| 3..n | execution | The procedure(s) |
| n+1 | example | End-to-end worked example |
| n+2 | verification | Mechanical checklist |
| n+3 | guardrail | Anti-patterns / "never do these" |
| n+4..m | anti_pattern | (Optional) surgical bug-flagging fragments added after pilot trace evidence |

Sequence ordering matters because the trial harness presents fragments to the LM in this order, and arm definitions in task fixtures reference fragments by sequence. Re-ordering an existing skill's fragments breaks every arm definition that references it.

### 2.5 Domain tags

Per `docs/skillsmith-authoring-reference.md` §5: tags drive BM25 + embedding retrieval. Hard cap 20. Tier soft ceilings vary. **Author tags from the canonical query surface, not from the skill's content** — i.e., what would an operator type into the search to find this skill? Tags should match operator vocabulary, not author internal vocabulary.

System skills MUST have empty `domain_tags` (rule `system-empty`).

---

## Phase 3 — QA Gate

The QA gate (`src/skillsmith/authoring/qa_gate.py`) runs three stages and routes to one of four next states. Reading the QA report and iterating is half the authoring work.

### 3.1 Run the gate

```bash
# Run on all drafts in pending-qa/
python -m skillsmith.authoring qa_gate

# Run on a single draft
python -m skillsmith.authoring qa_gate --skill-id <skill_id>

# Common flags
python -m skillsmith.authoring qa_gate --bounce-budget 5    # default 3
python -m skillsmith.authoring qa_gate --strict             # warnings → errors
python -m skillsmith.authoring qa_gate --no-llm             # skip stage 3 (deterministic only)
```

### 3.2 The three stages

**Stage 1 — Deterministic structural lint** (`run_deterministic`):
- Schema validation (top-level fields per §1, fragment fields per §1.2)
- Category vocabulary (per skill_class)
- Fragment-type validity (`setup`, `execution`, `verification`, `example`, `guardrail`, `rationale`, `anti_pattern`)
- Word-count thresholds (warn at 80/800, hard at 20/2000)
- Contiguity check (every fragment.content is a contiguous slice of raw_prose)
- Tag count (hard cap 20)
- System-skill rules (`sys-` prefix, empty `domain_tags`, `phase_scope` validity)

Stage 1 failures produce structured errors that almost always require source-level edits, not surface tweaks.

**Stage 2 — Dedup** (`run_dedup`):
- Against current corpus: any fragment whose content is too similar to an existing fragment elsewhere in the corpus is flagged
- Same-skill dedup: two fragments in the same skill with overlapping content fail

Dedup failures usually mean either (a) the new skill duplicates content already covered by another skill (consolidate or scope down) or (b) the author wrote a fragment that paraphrases an earlier fragment in the same skill (consolidate).

**Stage 3 — Critic LLM** (`run_critic`):
- Reads the YAML + the dedup hits + the source SKILL.md
- Produces structured verdict: `approve | revise | reject` with `blocking_issues`, `per_fragment_notes`, `tag_verdicts`, `suggested_edits`
- Writes report to `<skill_id>.qa.md` next to the YAML

Stage 3 verdict drives routing.

### 3.3 Reading the QA report

The `<skill_id>.qa.md` report is the operator's working artifact. Sections:

| Section | What to do with it |
|---------|---------------------|
| `summary` | One-paragraph verdict from the critic. Read first. |
| `blocking_issues` | Each entry must be addressed before re-submission. Line-level edits. |
| `per_fragment_notes` | Fragment-by-fragment commentary. Often surfaces fabrication (R7) or import discipline (R2) issues. |
| `tag_verdicts` | Tag-level approve/revise/reject from semantic lint. Drives retrieval quality. |
| `suggested_edits` | Author's choice — apply if they improve, ignore if they don't. |

### 3.4 Routing and iteration

Per `qa_gate.route()`:

| Verdict | Destination | Next action |
|---------|-------------|--------------|
| approve | `pending-review/` | Operator manually reviews, moves to ingest |
| revise | `pending-revision/` | Author addresses `blocking_issues`, moves back to `pending-qa/`, re-runs gate |
| reject | `rejected/` | Skill design is fundamentally wrong; restart from Phase 1 |
| needs-human | `needs-human/` | Bounce budget exceeded (default 3); a human must intervene |

### 3.4a Stop-the-line: local-author + uncited verification

**If the authoring agent was a local model (per §2.1a), apply this additional gate before ingest:**

Inspect the verification fragment (typically `:7` per gold-standard convention) for *quoted source snippets with date-stamps*, not boilerplate phrasing. The pattern to require:

```markdown
- [ ] <claim> — verified against <source URL or doc reference> on <YYYY-MM-DD>:
      "<short verbatim snippet from the canonical source>"
```

The pattern to reject:

```markdown
- [ ] <claim> — see official documentation
- [ ] <claim> — per the standard
- [ ] <claim>  (no source attribution at all)
```

The first pattern is verifiable. The second is fabrication-shaped — the agent is going through R3 motions without grounding. Local 27B–35B models drift into the second pattern more often than Opus does, and the deterministic + dedup stages don't catch this; only the critic Stage 3 might, and only if the critic prompt is tuned to flag uncited verification items.

**Action when uncited verification is found in a `pending-review/` skill authored by a local model:**

1. Do NOT auto-approve to ingest, even if the QA gate's overall verdict is `approve`.
2. Route the YAML manually to `pending-revision/` with a blocking_issue noting "verification fragment lacks quoted source snippets per R5 date-stamping discipline."
3. The author re-fetches the canonical source, quotes the relevant snippet, date-stamps it, and re-submits.

This stop-the-line applies regardless of whether the qa_gate critic Stage 3 flagged it. Local-model authoring earns this extra gate because the pilot validated Qwen3.6-27B at the critic role but did NOT validate it at the source-verification authoring role; first-pass drafting fabrication risk is real and the verification fragment is the load-bearing audit point.

When in doubt about whether a citation is real: open the URL, find the snippet, confirm. Once. Then promote.

### 3.5 When to escalate vs iterate

Iterate if blocking_issues are concrete and addressable in line-level edits.

Escalate (move to `needs-human/`) if any of:
- The critic's verdicts are inconsistent across runs (instability suggests the skill is fundamentally ambiguous)
- You've revised 3 times and the same blocking issues recur (suggests source SKILL.md is wrong)
- The critic flags fabricated content (R7) that you can't replace with verified examples
- The critic flags scope drift (skill is trying to cover too much)

Per the bounce-budget design, the system enforces this — after 3 revisions you can't keep iterating without operator escalation.

### 3.6 Local sanity checks before re-submitting

```bash
# Type + lint clean
ruff check . && ruff format --check . && uv run pyright

# Validate without ingesting
python -c "from skillsmith.ingest import _load_yaml, _validate, _lint; \
           r = _load_yaml('skill-source/pending-qa/<skill_id>.yaml'); \
           print('errors:', _validate(r)); \
           print('warnings:', _lint(r))"

# Re-run QA on this single skill
python -m skillsmith.authoring qa_gate --skill-id <skill_id>
```

---

## Phase 4 — Ingest into LadybugDB

Once the skill lives in `pending-review/` and you've manually reviewed the QA report, run the ingest CLI to load it into the runtime graph store.

### 4.1 Storage architecture (relevant context)

```
LadybugDB (Kuzu graph)              DuckDB (skills.duck)
  ├── Skill nodes                     ├── fragment_embeddings
  ├── SkillVersion nodes              ├── composition_traces
  ├── Fragment nodes                  └── pilot_trials (instrumented runs)
  └── relationships
      (Skill→SkillVersion,
       SkillVersion→Fragment,
       Fragment→Fragment ordering)
```

LadybugDB stores the *graph structure* — which fragments belong to which skill, which version is current, what the lineage is. It does NOT store embeddings. Per the v5.3 directive (`src/skillsmith/storage/ladybug.py` docstring), the Kuzu VECTOR extension is not loaded; it's incompatible with restartable FastAPI service lifecycle.

DuckDB stores the *embedding vectors* and BM25 indices. Embeddings are populated by a separate reembed pass (Phase 5).

### 4.2 Run the ingest

```bash
# Single skill
python -m skillsmith.ingest skill-source/pending-review/<skill_id>.yaml

# Common flags
python -m skillsmith.ingest path/to/skill.yaml --force      # overwrite existing skill_id (creates new SkillVersion)
python -m skillsmith.ingest path/to/skill.yaml --strict     # warnings → errors
python -m skillsmith.ingest path/to/skill.yaml --yes        # skip confirmation prompt

# Batch ingest a directory
python -m skillsmith.ingest skill-source/pending-review/

# Exit codes
#   0   success
#   1   usage error
#   2   validation error
#   3   DB error
#   4   duplicate (skill_id or canonical_name already in corpus; not an error in install-pack flow)
```

### 4.3 What ingest does

1. Loads the YAML
2. Re-runs `_validate` + `_lint` (defense-in-depth even though qa_gate already ran)
3. Resolves `tier` from sibling `pack.yaml` if not in the skill itself
4. Begins a Kuzu transaction
5. Creates a `Skill` node (or finds existing)
6. Creates a new `SkillVersion` node, links to Skill, marks as current
7. Creates `Fragment` nodes for every fragment, links to SkillVersion in sequence order
8. Initializes fragment embeddings to zero in DuckDB (Phase 5 populates real vectors)
9. Writes `change_summary` to the SkillVersion (R6 honesty trail)
10. Commits

If anything fails, the transaction rolls back. The `--force` flag is required to overwrite an existing `skill_id` — without it, ingest exits with code 4 (duplicate).

### 4.4 Verify the ingest

```bash
# List all skills currently in the corpus
python -m skillsmith.reads list-skills

# Show a single skill's full record
python -m skillsmith.reads show-skill <skill_id>

# Show the version history
python -m skillsmith.reads versions <skill_id>
```

If the skill doesn't appear, check the ingest exit code and DB logs.

---

## Phase 5 — Embedding & Indexing

Fragment embeddings drive vector retrieval; BM25 indices drive lexical retrieval. Both must be populated before the skill is usable in a retrieval-routed query.

### 5.1 Run the reembed pass

```bash
# Reembed a single skill's fragments (post-ingest)
python -m skillsmith.reembed --skill-id <skill_id>

# Reembed all skills in a pack
python -m skillsmith.reembed --pack <pack-name>

# Reembed everything (slow; only after embedding-model migrations)
python -m skillsmith.reembed --all
```

The reembed pass:
1. Reads fragments from LadybugDB
2. Calls the embedding model (default: Ollama with the configured embedder; see `docs/skillsmith-model-selection.md` for current model choices)
3. Writes vectors into `fragment_embeddings` in DuckDB
4. Updates BM25 indices via DuckDB FTS

Embedding dimension is enforced — `EmbeddingDimMismatch` is raised if the configured embedder's output dim differs from what the DuckDB schema expects. If you're migrating embedding models, expect to re-embed the entire corpus (`--all`).

### 5.2 Verify embeddings populated

```bash
# Quick sanity check via DuckDB shell
python -c "
import duckdb
conn = duckdb.connect('data/skills.duck')
n_zero = conn.execute('SELECT COUNT(*) FROM fragment_embeddings WHERE embedding[1] = 0').fetchone()[0]
n_total = conn.execute('SELECT COUNT(*) FROM fragment_embeddings').fetchone()[0]
print(f'{n_zero}/{n_total} fragments still zero-vector (need reembed)')
"
```

If your newly-ingested skill's fragments show as zero-vector, the reembed pass didn't run for them.

### 5.3 Tag-level retrieval (semantic lint output)

If your skill went through the full Stage 3 critic, `tag_verdicts` may have flagged tags as `revise` (semantic-lint mismatch with content). Re-running ingest after fixing tags re-creates the fragment embeddings; running reembed alone does not refresh the LadybugDB graph.

---

## Phase 6 — Retrieval Verification

A skill that ingests cleanly and embeds cleanly can still fail in production retrieval if its tags or content don't match real queries. Verify before promoting.

### 6.1 Test against representative queries

Use the retrieval CLI:

```bash
# Show top-K hits for a query
python -m skillsmith.retrieval search "<representative operator query>"

# With phase + category filters
python -m skillsmith.retrieval search "<query>" --phase build --category engineering
```

For each query you expect should retrieve your new skill, verify it appears in the top results. If it doesn't:

- BM25 miss: tags don't include the operator's vocabulary. Add tags from the actual query surface.
- Vector miss: fragment content is too generic / abstract. Tighten the language.
- Filter miss: phase/category mismatch. Re-check `phase_scope` / `category_scope` for system skills, or `category` for domain skills.

### 6.2 Test applicability

If your skill has `applicability` predicates (per `src/skillsmith/applicability.py`), test them against representative request payloads. Applicability filtering happens at retrieval time as a post-filter — if it's wrong, the skill will be retrieved by similarity but discarded before reaching the execution model.

### 6.3 Test in the live trial harness (optional but recommended)

If you have a representative task fixture, run the skill through the trial harness to verify it actually drives the execution model toward the intended behavior:

```bash
# See experiments/skill-tax/harness/ for the harness
LM_STUDIO_BASE_URL=http://localhost:1234 \
SKILLS_DUCK_PATH=data/skills.duck \
.venv/bin/python experiments/skill-tax/harness/run_trial.py \
    --task <fixture> --arm arm_b --run 1 --temperature 0.0 --trial-class arm_comparison
```

For a new domain, this is M5-style verification. The pilot's findings show that fragments alone don't guarantee functional pass; verification surfaces whether the skill produces the *behavior change* you intended, not just structurally-clean output.

---

## Phase 7 — Promote / Release

Once retrieval verification is clean:

1. **Update the pack's `skills:` manifest** in `pack.yaml`:
   ```yaml
   skills:
     - skill_id: <new-skill-id>
       fragment_count: <n>
       tier: <tier>
   ```
2. **Bump the pack version** per `docs/PACK-AUTHORING.md` §Versioning (semver: minor for additive changes, major for breaking).
3. **Move the YAML** from `pending-review/` to `seeds/packs/<pack>/<skill-id>.yaml` (the canonical pack location).
4. **Update `docs/skillsmith-pack-inventory.md`** if this is a new pack or significantly extends an existing one.
5. **Run the pack-level QA**:
   ```bash
   python -m skillsmith.authoring pack-qa --pack <pack-name>
   ```
   This validates the pack manifest matches the actual skill files, fragment counts are accurate, and tier assignments are consistent.
6. **Commit** with a `skills:` or `skill:` prefix per repo convention. Reference the SKILL.md source path so reviewers can trace from skill back to source.

---

## Phase 8 — Maintenance: versioning, updates, deprecation

### 8.1 Updating an existing skill

Every change to a skill creates a new `SkillVersion` in LadybugDB. The previous version remains in the graph but is no longer "current." This preserves the audit trail for any past trial that referenced the old version.

To update:

1. Edit the skill YAML in place (or in `skill-source/pending-qa/`).
2. Update `change_summary` to describe the change (R6 — never delete prior provenance).
3. Re-run QA gate.
4. Re-ingest with `--force`. The `--force` is required because the `skill_id` already exists; it tells ingest to create a new `SkillVersion` rather than reject as duplicate.
5. Re-run reembed for that skill.
6. Re-run retrieval verification.

**Pilot example (M4):** the M4 milestone added a lifespan-preservation guardrail to `fastapi-middleware-patterns:8`. The change was a single fragment edit. The procedure was: edit the YAML, update `change_summary` with reference to the M3 architectural finding, re-ingest, re-embed, re-run T3a/T3b/T4. The pilot's M4 trials directly validated the updated skill.

### 8.2 Adding fragments to an existing skill

Adding a new fragment (e.g., the M7 anti-pattern fragments at `webhook-patterns:9-12`) is the same flow as updating, but with new fragment sequence numbers appended:

1. Add new fragments to the YAML at the next-available sequence numbers.
2. Update `change_summary` to note the addition and rationale.
3. Re-ingest with `--force`.
4. **Important:** any task fixture or arm definition referencing fragments by sequence may need to be updated to include the new sequences. The pilot's `T1.arm_b_plus` arm in `T1.yaml` was added specifically to include the new anti-patterns alongside the original arm_b set.

### 8.3 Deprecating a skill

A skill is deprecated, not deleted. Deletion would break the audit trail of any trial that referenced it.

```bash
# Mark a skill deprecated; future retrievals exclude it
python -m skillsmith.reads deprecate-skill <skill_id> --reason "<reason>"
```

This sets a flag on the Skill node. Retrieval queries skip deprecated skills. Existing SkillVersion / Fragment nodes remain intact.

### 8.4 The R6 provenance trail

`change_summary` is not optional and not cosmetic. It's the operator's audit trail. Every version's change_summary is preserved in the graph, queryable via:

```bash
python -m skillsmith.reads versions <skill_id>
```

When investigating "why did this skill behave differently than the trial showed?", the version history is where the answer lives.

---

## Phase 9 — Pilot-derived authoring discipline

The skill-tax pilot (M2–M8, see `experiments/skill-tax/reviews/_POC_FINAL.md`) produced specific authoring discipline that supplements the schema/rules in `skillsmith-authoring-reference.md`. These are heuristics validated by the pilot's data:

### 9.1 Anchoring fragments are load-bearing for execution-routed queries

**Pilot evidence:** spec C1 ("anchoring fragments NOT load-bearing") was refuted by T4's arm-cell split. Dropping rationale + example fragments between Arm A (8 frags) and Arm B (6 frags) caused T4 pass rate to collapse from 100% to 0%. The dropped fragments carried the "preserve other behavior" signal that prevented wholesale-rewrite scope_violation.

**Authoring implication:** for any domain skill targeting cognitive shapes that involve modifying existing code (T4 shape: targeted local refactor), include rationale + example fragments. These earn their context budget. Drop them only for execution arms where context budget pressure is explicit and the cognitive shape is bounded net-new generation (T1 shape).

### 9.2 Fragment templates compete with task-specific seed content

**Pilot evidence:** 18/18 T3a + T3b arm-comparison trials in M2/M3 wrote a lifespan that dropped the seed's `CREATE TABLE` statement. The model substituted the lifespan template from `fastapi-middleware-patterns:2` (or `:6`) for the seed's task-specific lifespan. M4's added guardrail did not fix this because the model paraphrased the guardrail in comments while still violating it in code.

**Authoring implication:** when authoring fragments that show implementation templates (lifespan stubs, route stubs, middleware stubs), explicitly frame them as **starter shapes**, not authoritative replacements. Use language like "minimum starter shape — extend with task-specific setup" rather than presenting templates as canonical reference implementations. Add a guardrail anti-pattern fragment if production traces show models substituting template-for-seed.

### 9.3 Anti-pattern fragments have specific operational scope

**Pilot evidence:** M7's 4 surgical anti-pattern fragments (`webhook-patterns:9-12`) targeted exact bugs observed in M5 trials. The fragments produced 0 functional-pass lift on T1 across 4 small models (1.5B–3.8B). M8 self-QA pass also produced 0 functional-pass lift. The 1.5B Coder kept producing positional `split(",")[N]` 5/5 times despite anti-pattern :9 being in its context.

**Authoring implication:** anti-pattern fragments earn their keep at *higher* execution-model tiers where the model can actually act on the negative signal. They do not compensate for parameter-application failure at small scale. Author them when (a) production trace data shows the bug, (b) the deployed execution model is at or above the parameter-application threshold for the task surface. Do not author them speculatively — they cost context without measurable benefit below the threshold.

### 9.4 Format-compliance is a separate axis from substantive correctness

**Pilot evidence:** M8 self-QA pass lifted format compliance dramatically (Qwen2.5-Coder-3B and Phi-4-mini both went from 0/5 strict-parse to 5/5 strict-parse) but lifted functional pass in zero cases. The cognitive task of "check format directive" is within the parameter floor; "recognize own buggy code against anti-pattern description" is below.

**Authoring implication:** if your skill is for a deployment target where output-format reliability matters (any production code-generation pipeline), the skill's fragments should make format directives unambiguous. Don't bury format constraints in execution prose. If a workflow self-QA pass is part of the deployment, anti-pattern fragments and format directives are good levers; substantive bug-correction fragments are not.

### 9.5 Cognitive-shape × parameter-size is the deployment matrix

**Pilot evidence:** the cognitive-shape × parameter-size matrix in `_POC_FINAL.md` §5 prescribes which model size handles which cognitive shape. Skills can shift each cognitive shape's parameter floor downward but cannot replace the matching itself.

**Authoring implication:** when authoring a skill, explicitly identify the cognitive shape(s) it targets and the smallest model size that should retrieve it. Encode this implicitly via fragment composition — a skill aimed at small-Coder targeted-refactor work has different fragment emphasis than one aimed at 30B-class composition work.

This matters at retrieval time: if the same skill is retrieved by a generalist routing to a 1.5B execution model, the skill should serve that pairing or the retrieval should not fire. Tag and `category_scope` discipline expresses this.

---

## Phase 10 — Common authoring pitfalls

(Supplements `docs/skillsmith-authoring-reference.md` §8 with pilot-surfaced patterns.)

### 10.1 The "fragment template wins" pattern

Authoring a setup or example fragment that shows a *complete* lifespan or middleware stack risks the M3/M4 lifespan-rewrite pattern: at retrieval time, the model echoes the template instead of preserving task-specific seed content.

**Mitigation:** explicitly frame templates as starter shapes; add anti-pattern fragments that warn against template-for-seed substitution; pair examples with rationale that emphasizes "preserve other behavior."

### 10.2 The "training-data pre-empts the fragment" pattern

Authoring fragments that document a procedure the model already knows from training data risks fragment-faithful but training-data-driven behavior. The pilot's T1 trials passed 100% via Stripe SDK shortcut even when the fragment showed manual HMAC; the model picked the SDK path it knew.

**Mitigation:** in domains with strong training-data coverage, explicitly mark which path the skill prescribes vs which path the SDK or training data would default to. Per-vendor nuance fragments (like webhook-patterns:4 for Stripe vs Slack vs Standard Webhooks signature schemes) are specifically valuable here because they document divergent behavior the model wouldn't pick correctly without guidance.

### 10.3 The "anti-pattern without pointer" pattern

Anti-pattern fragments that name a bug without pointing back to the correct procedure risk leaving the model ungrounded — model knows what NOT to do, invents its own (possibly wrong) Y.

**Mitigation:** every anti-pattern fragment ends with `**Correct approach:** see <skill:fragment_seq>.` Pointer is non-negotiable.

### 10.4 The "speculative anti-pattern" pattern

Authoring anti-pattern fragments based on what authors imagine the model *might* do wrong, rather than what production traces show it actually does wrong, costs context budget without benefit.

**Mitigation:** anti-pattern fragments require trace evidence. If you don't have the trace, don't author the fragment.

### 10.5 The "wrong cognitive shape" pattern

A skill that mixes guidance for net-new generation (T1 shape) and targeted refactor (T4 shape) and multi-skill composition (T3a/T3b shape) tries to be everything for everyone. At retrieval time it gets selected for tasks where its emphasis is wrong.

**Mitigation:** scope each skill to one (or at most two adjacent) cognitive shapes. If a domain spans multiple shapes, author multiple skills — one for each — and let the generalist's phase routing + tags differentiate them.

---

## Appendix A — File map

| Path | Purpose |
|------|---------|
| `skill-source/<skill_id>/SKILL.md` | Source markdown (canonical prose) |
| `skill-source/pending-qa/<skill_id>.yaml` | Draft awaiting QA gate |
| `skill-source/pending-review/<skill_id>.yaml` | QA-passed, awaiting human review + ingest |
| `skill-source/pending-revision/<skill_id>.yaml` | QA returned `revise`; iterate |
| `skill-source/rejected/<skill_id>.yaml` | QA returned `reject`; archive |
| `skill-source/needs-human/<skill_id>.yaml` | Bounce budget exceeded; manual escalation |
| `skill-source/<skill_id>.qa.md` | QA gate report (sibling of YAML) |
| `seeds/packs/<pack>/<skill_id>.yaml` | Production canonical location after promote |
| `seeds/packs/<pack>/pack.yaml` | Pack manifest |
| `data/skills.duck` | DuckDB: fragment_embeddings + composition_traces |
| `data/ladybug.kuzu` | Kuzu graph: Skill / SkillVersion / Fragment |

## Appendix B — CLI quick reference

```bash
# AUTHORING
python -m skillsmith.authoring author --pack <pack>
python -m skillsmith.authoring qa_gate [--skill-id <id>] [--bounce-budget N] [--strict] [--no-llm]

# INGEST
python -m skillsmith.ingest <yaml-path> [--force] [--strict] [--yes]
python -m skillsmith.ingest <directory>                          # batch

# EMBEDDING
python -m skillsmith.reembed --skill-id <id>
python -m skillsmith.reembed --pack <pack>
python -m skillsmith.reembed --all                               # full corpus

# READS / VERIFY
python -m skillsmith.reads list-skills
python -m skillsmith.reads show-skill <id>
python -m skillsmith.reads versions <id>
python -m skillsmith.reads deprecate-skill <id> --reason "<r>"
python -m skillsmith.retrieval search "<query>" [--phase <p>] [--category <c>]

# PACK-LEVEL
python -m skillsmith.authoring pack-qa --pack <pack>

# TRIAL HARNESS (pilot infrastructure; useful for skill behavior verification)
LM_STUDIO_BASE_URL=http://localhost:1234 \
SKILLS_DUCK_PATH=data/skills.duck \
.venv/bin/python experiments/skill-tax/harness/run_trial.py \
    --task <fixture> --arm <arm> --run <n> --temperature 0.0 --trial-class arm_comparison
```

## Appendix C — Author's pre-flight checklist

Before submitting a new skill to QA:

- [ ] SKILL.md source written; raw_prose in YAML is whitespace-normalized identical
- [ ] One-sentence reason-to-exist articulable
- [ ] Cognitive shape(s) the skill serves identified
- [ ] Skill class (`domain` / `system` / `workflow`) decided; sys-* prefix if system
- [ ] Tier resolved (or pack.yaml exists with tier)
- [ ] All non-stdlib symbols have an `import` once (R2)
- [ ] Verification items are mechanically checkable (R3)
- [ ] Examples cover happy + failure + edge case (R4)
- [ ] Date-stamps on version-specific claims (R5)
- [ ] `change_summary` honest + specific (R6)
- [ ] No fabricated examples (R7) or all flagged
- [ ] Rationale fragments include lexical anchors for obvious queries (R8)
- [ ] Anti-pattern fragments (if any) have pointer-back to correct procedure
- [ ] Domain tags reflect operator vocabulary, not author internal vocabulary
- [ ] Tag count ≤ 20

Before promoting from pending-review to production:

- [ ] QA gate verdict: `approve`
- [ ] QA report read end-to-end; `suggested_edits` triaged
- [ ] Ingest dry-run clean (`_validate` + `_lint` no errors)
- [ ] Ingest succeeded; `reads list-skills` shows the new skill
- [ ] Reembed completed; fragments not zero-vector
- [ ] Retrieval verification: representative queries return the skill in top-K
- [ ] (If applicable) trial harness verification on a representative task fixture
- [ ] Pack manifest updated with new skill + fragment count
- [ ] Pack version bumped per semver
- [ ] `docs/skillsmith-pack-inventory.md` updated if new pack or material extension

---

## Appendix D — Source documents and where to read what

| Need | Read |
|------|------|
| Schema field definitions | `docs/skillsmith-authoring-reference.md` §1 |
| Pack-level structure | `docs/PACK-AUTHORING.md` |
| Contract rules (R1–R8, W1, C1) | `docs/skillsmith-authoring-reference.md` §3 |
| Gold-standard skill examples | `docs/skillsmith-authoring-reference.md` §4 + `experiments/skill-tax/skills/webhook-patterns.yaml` |
| Lint behavior (deterministic / dedup / critic) | `docs/skillsmith-authoring-reference.md` §7 + `src/skillsmith/authoring/qa_gate.py` |
| Source discipline + fabrication prevention | `docs/skillsmith-authoring-reference.md` §10 |
| Pilot findings on fragment composition | `experiments/skill-tax/reviews/_POC_FINAL.md` §4 + this doc §9 |
| Storage architecture (Kuzu + DuckDB split) | `src/skillsmith/storage/ladybug.py` docstring + `src/skillsmith/storage/vector_store.py` |
| Embedding model selection | `docs/skillsmith-model-selection.md` |
| Pack inventory + tier ladder | `docs/skillsmith-pack-inventory.md` |
| Architecture spec (full system) | `docs/ARCHITECTURE.md` + `docs/skillsmith-architecture-spec_update.md` |
| Pilot's authoring provenance | `experiments/skill-tax/skills/AUTHORING_LOG.md` |

---

## Bottom line

Authoring a skill that lints clean is straightforward — the schema is well-defined and the QA gate enforces it. Authoring a skill that *moves the needle in production* requires the pre-authoring design discipline (Phase 1) and the pilot-derived fragment-composition guidance (Phase 9). The QA gate doesn't catch "this skill is for the wrong cognitive shape" or "anti-pattern fragments without trace evidence" — those are author judgment calls the system trusts you to make.

The full lifecycle takes a working skill from "I have a hunch this knowledge should be a skill" through "this skill is improving production retrieval-routed inference at the deployed execution-model tier." Skipping phases (especially Phase 1 design and Phase 6 retrieval verification) produces skills that pass linting and fail in production.
