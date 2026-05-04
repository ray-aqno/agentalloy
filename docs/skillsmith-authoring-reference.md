# Skillsmith Authoring Reference

The tactical contract for any agent authoring skills against the v1 corpus. Companion to:

- `docs/skillsmith-architecture-spec_update.md` — corpus contract (why)
- `docs/skillsmith-pack-inventory.md` — prioritized pack list (what)
- `docs/skillsmith-model-selection.md` — model routing for authoring (how to spend cycles)

This doc is the equivalent of an SDD spec template: schema, rules, examples, source discipline. It is generated from the codebase and must be kept current as the schema evolves. When in doubt, the cited source files are the source of truth — not this document.

**Last verified:** 2026-04-30 against `main` at `8228e6a` (post-routing-reform-v1).

---

## 1. Skill YAML Schema

Source: `src/skillsmith/reads/models.py`, `src/skillsmith/ingest.py:_validate` (lines 480–565), `fixtures/skill-qa-agent.md`.

### Top-level fields (all required unless marked optional)

| Field | Type | Required | Notes |
|---|---|---|---|
| `skill_type` | `"domain" \| "system"` | yes | Hard-enforced at ingest. System skills must additionally have `skill_id` starting with `sys-`. |
| `skill_id` | `str` | yes | Globally unique. Hyphenated, lowercase. Collision blocks ingest unless `--force`. |
| `canonical_name` | `str` | yes | Human-readable display title. |
| `category` | `str` | yes | Validated against the per-class vocabulary (below). |
| `skill_class` | `"domain" \| "system" \| "workflow"` | yes | Retrieval contract. See §1.3. |
| `domain_tags` | `list[str]` | yes (empty for system) | Drives BM25 + embedding retrieval. Hard cap 20; per-tier soft ceilings in §5. System skills MUST be `[]` (rule `system-empty`). |
| `always_apply` | `bool` | yes (default `false`) | System skills only. Mutually informative with `phase_scope`/`category_scope`. |
| `phase_scope` | `list[str] \| null` | optional | System skills. Allowed values: `design`, `build`, `review` (`_VALID_PHASES`). |
| `category_scope` | `list[str] \| null` | optional | System skills. |
| `author` | `str` | optional (default `"operator"`) | Authoring entity name. |
| `change_summary` | `str` | yes | R6 honesty: state authorship clearly. See §3 (R6). |
| `raw_prose` | `str` | yes | Canonical source text. Every fragment's `content` must be a contiguous slice (whitespace-normalized). |
| `fragments` | `list[FragmentRecord]` | yes (≥1) | See §1.2. |
| `tier` | `str \| null` | optional | Resolved from sibling `pack.yaml` if absent. See §2. |

### 1.1. Category vocabularies

Source: `src/skillsmith/ingest.py:44-49`.

```python
_VALID_SYSTEM_CATEGORIES = {"governance", "operational", "tooling", "safety", "quality", "observability"}
_VALID_DOMAIN_CATEGORIES = {"engineering", "ops", "review", "design", "tooling", "quality"}
```

A skill in the wrong category vocabulary is a hard validation failure. Workflow skills use the domain vocabulary.

### 1.2. Fragment schema

Source: `src/skillsmith/ingest.py:103-106`.

```python
@dataclass
class FragmentRecord:
    sequence: int       # 1-indexed order within skill
    fragment_type: str  # one of _VALID_FRAGMENT_TYPES
    content: str        # contiguous slice of raw_prose modulo whitespace
```

Fragments must be **contiguous slices of `raw_prose`**. `_lint` rejects content that doesn't match raw_prose under whitespace normalization with the message *"drift breaks BM25/full-text retrieval."* This is non-negotiable — paraphrasing the source into fragment content silently breaks lexical retrieval.

### 1.3. `skill_class` semantics

Source: `src/skillsmith/reads/models.py`, `src/skillsmith/applicability.py`.

- **`domain`** — retrieved by embedding + BM25 over `domain_tags` and prose. Tag policy applies.
- **`system`** — always-injected (or scoped by phase/category). `domain_tags` MUST be `[]`. Either `always_apply: true`, or a non-empty `phase_scope`, or a non-empty `category_scope`.
- **`workflow`** — process-position skills. Retrieved alongside `domain` skills. Must include ≥1 marker from `WORKFLOW_POSITION_MARKERS` (rule W1):

```python
WORKFLOW_POSITION_MARKERS = {
    "sdd", "phase:spec", "phase:design", "phase:plan", "phase:testgen",
    "phase:build", "phase:verify", "phase:deliver",
    "code-review", "release", "incident", "rfc",
}
```

### 1.4. Annotated example

See §4 for full gold-standard YAMLs. Minimal annotated skeleton:

```yaml
skill_type: domain                                  # "domain" or "system"
skill_id: webhook-patterns                          # globally unique, kebab-case
canonical_name: Webhook Patterns (HMAC, Replay, …)  # display title
category: engineering                               # from domain vocabulary
skill_class: domain                                 # "domain" | "system" | "workflow"
domain_tags: [webhooks, hmac, signing, …]           # ≤ tier soft_ceiling
always_apply: false                                 # system skills only
phase_scope: null                                   # system skills only
category_scope: null                                # system skills only
author: navistone
change_summary: Initial authoring (verified 2026-04-28). Sources — stripe.com/docs, …
raw_prose: |
  # Webhook Patterns
  ## Overview
  HMAC signing, replay protection, retry-with-backoff, …
fragments:
  - sequence: 1
    fragment_type: rationale     # one of {setup, execution, verification, example, guardrail, rationale}
    content: |
      # Webhook Patterns
      HMAC signing, replay protection, …   # contiguous slice of raw_prose
  - sequence: 2
    fragment_type: setup
    content: |
      ## Standards landscape (verified 2026-04-28)
      …
```

---

## 2. Pack YAML Schema

Source: `src/skillsmith/install/subcommands/install_pack.py`, `docs/PACK-AUTHORING.md`, real pack manifests under `src/skillsmith/_packs/*/pack.yaml`.

### Required fields

```yaml
name: <pack-name>           # lowercase, kebab-case, matches directory
version: <semver>           # bump on any skill content change
tier: <one-of-10-values>    # see §2.1
description: "<one-line>"   # shown in install picker
author: navistone           # or authoring entity
embed_model: qwen3-embedding:0.6b  # model YAMLs were authored against (soft-warned on mismatch)
embedding_dim: 1024         # hard-blocks install on mismatch
license: MIT
skills:                     # required inventory check
  - skill_id: <id>
    file: <filename>.yaml
    fragment_count: <N>
```

### Optional fields

```yaml
homepage: <url>
always_install: false       # only true for foundation packs (core, engineering)
depends_on: [pack1, pack2]  # other packs whose skills are pulled in alongside
```

### 2.1. Tiers

Source: `src/skillsmith/install/subcommands/install_pack.py:_VALID_PACK_TIERS`, `scripts/migrate-seeds-to-packs.py:PACK_TIERS`.

| Tier | Meaning | Examples |
|---|---|---|
| `foundation` | always-installed process & generic engineering | core, engineering |
| `language` | "I write code in X" | python, typescript, go, rust, nodejs |
| `framework` | "I build apps with framework X" | react, nextjs, fastapi, nestjs, fastify, vue |
| `store` | "I read/write data via system X" | postgres, mongodb, redis, s3, temporal, prisma |
| `cross-cutting` | capability X regardless of stack | auth, security, observability |
| `platform` | "I run/ship code on infra X" | containers, iac, cicd, monorepo |
| `tooling` | dev-loop tools | testing, linting, vite, mocha-chai |
| `domain` | application domain | agents, ui-design, data-engineering |
| `protocol` | wire format | graphql, webhooks, websockets |
| `workflow` | process position | sdd, code-review (planned) |

`_VALID_PACK_TIERS` and `PACK_TIERS` are guarded by `tests/install/test_pack_tier_registry_consistency.py` against drift.

### 2.2. Pack-tier ↔ skill-class relationship

The pack's `tier` does **not** dictate the skill's `skill_class`. A `workflow`-tier pack contains `workflow` skills; most other tiers mostly contain `domain` skills. System skills sit in the `core` and `engineering` foundation packs.

The `tier` value flows from `pack.yaml` to each skill's `tier` field via `skill_tier.resolve_skill_tier()` (walks up the directory tree to the sibling `pack.yaml`). It governs the **tag soft-ceiling** for that skill (see §5).

### 2.3. Real pack.yaml (verbatim, `webhooks`)

```yaml
name: webhooks
version: 1.0.0
tier: protocol
description: Webhook receiver + sender patterns — HMAC-SHA256 signing, replay protection,
  retry with exponential backoff + jitter, dead-letter queue. Stripe / GitHub / Standard
  Webhooks reference.
author: navistone
embed_model: qwen3-embedding:0.6b
embedding_dim: 1024
license: MIT
homepage: https://github.com/nrmeyers/skillsmith
always_install: false
depends_on:
- engineering
- nodejs
skills:
- skill_id: webhook-patterns
  file: webhook-patterns.yaml
  fragment_count: 8
```

---

## 3. The R1–R8 + W1, C1 Contract Rules

Canonical source: **`fixtures/skill-authoring-guidelines.md`**. Read that file directly when authoring; this section is a structured reference, not a replacement.

### R1 — Fetch authoritative docs before authoring against fast-moving APIs

For frameworks <2 years old, ML/agent SDKs, and vendor SDKs (Anthropic, Prisma, OTel, mongo Node driver, mocha+tsx loaders), fetch current docs via `ctx_fetch_and_index` BEFORE writing examples. Quote them when the example uses a non-trivial signature.

**Why**: training-data knowledge is allowed to be ~6 months stale on these APIs and routinely is. Batch-2 shipped wrong Prisma generator name, Mongo `Decimal128` shell-vs-driver syntax, mocha `loader:` field, OTel `resourceFromAttributes` because of stale recall.

**Lint enforcement**: semantic — the QA critic emits a `tag_verdicts[].rule = "R1"` verdict on tags whose underlying claim doesn't match current authoritative docs. If you can't cite a doc, drop the tag and the claim.

### R2 — Every non-stdlib name in a code block must show its `import` once

If a block references `Prisma.Decimal`, `Anthropic.Tool`, `PrismaClientKnownRequestError`, etc., at least one block in the same skill must show the `import` line. Examples without imports compile in nobody's editor.

**Lint enforcement**: mechanical (`lint_tags_mechanical.py`) — tag stems that overlap title stems get `verdict="redundant_with_title"`. The mechanical lint is for the tag policy face of R2; the import discipline is enforced via the QA critic's effectiveness rubric.

### R3 — Verification fragments are contracts; every item must be mechanically checkable

A verification item is a post-condition a downstream agent will check. Each item must be expressible as a one-line shell command, a single assertion, or a binary observation. **If you can't write the check, drop the item.** Vague items ("good practices followed", "config is sensible") and unverified claims ("env-var change requires server restart" — wrong; Vite watches `.env*`) do not survive this rule.

**Lint enforcement**:
- `R3-stem` — mechanical pairwise tag stem overlap → `verdict="synonym_of:<other>"`.
- `R3-syn` — semantic, the QA critic flags tags whose surface form differs but meaning duplicates an existing tag.

### R4 — Examples must cover the case-space, not just the happy path

Two failure modes:

- **Surface coverage**: when an example claims to cover a state machine, an enum, or a method set, enumerate every case and comment why each is or isn't handled. The webhook example (§4) demonstrates this with three explicit paths in one handler.
- **Edge trace**: walk one realistic edge case through the example before committing.

**Lint enforcement**: semantic — critic flags tags as `verdict="off_intent"` when the example claims to demonstrate a tag but only shows a happy path.

### R5 — Date-stamp version-specific or minimum-value claims

Numeric thresholds, version requirements, and minimums change. Append `(verified YYYY-MM-DD)` inline or in a footer `## Verified` block.

A reader six months out needs to know whether to trust the number or re-check. *"I don't know — go check"* beats a confident wrong number.

### R6 — Imports must label authorship honestly

In `change_summary`:
- Verbatim upstream prose: `imported verbatim from <upstream-path>`
- Scaffolded around upstream: `scaffold by skillsmith around upstream prose preserved in fragment <N>`

Never write *"imported"* when you authored most of the content.

### R7 — Fabricated examples must be flagged or replaced

If an example names a file path, function, domain term, or API that doesn't exist in any real codebase, prefix with `Illustrative — not from a real codebase:` or replace with a less specific schematic.

Made-up domain terms presented as canonical (`payments adapter`, `checkout aggregate`) mislead readers and anchor retrieval on fictional vocabulary.

### R8 — Rationale fragments need lexical anchors for the obvious query

Each rationale fragment must include ≥3 of the obvious query terms for the skill it explains. Pair with the fragment length floor (≥80 words) — short fragments need explicit lexical anchoring to compensate for the embedder's weakness on small inputs.

For a skill on architectural context: rationale must contain `architecture`, `architectural context`, `system map`, `module boundaries`. If those words aren't present, retrieval on *"how do I get higher-level architectural context?"* won't surface it.

### W1 — Workflow position marker (workflow skills only)

Workflow skills must carry ≥1 tag from `WORKFLOW_POSITION_MARKERS` (§1.3). Mechanical enforcement: missing marker → `verdict="missing_position_marker"` and the skill fails ingest validation.

### C1 — Promote the authoring contract to ingest-time lint

Recommendation from the 2026-04-28 corpus audit. As of routing-reform v1, this is partially landed:

- **Mechanical**: `lint_tags_mechanical.py` (tag policy face)
- **Semantic**: `lint_tags_semantic.py` (R1, R3-syn, R4 face)
- **Structural**: ingest validation enforces fragment word counts, contiguity, tag caps, fragment-type validity

The remaining C1 surface (rationale-quality, verification-quality semantic check) is on the v1 backlog.

---

## 4. Gold-Standard Skill Examples

The 2026-04-28 batch-3 review approved 5 skills as the current quality bar. Path: `src/skillsmith/_packs/{webhooks,graphql,observability,websockets,engineering}/`.

### 4.1. Protocol-tier domain skill: `webhook-patterns`

Full file at `src/skillsmith/_packs/webhooks/webhook-patterns.yaml`. Reproduced verbatim:

```yaml
skill_type: domain
skill_id: webhook-patterns
canonical_name: Webhook Patterns (HMAC Signing, Replay Protection, Retries, Dead-Letter)
category: engineering
skill_class: domain
domain_tags: [webhooks, hmac, hmac-sha256, signing, replay-protection, retries, exponential-backoff, dead-letter-queue, idempotency, stripe, github]
always_apply: false
phase_scope: null
category_scope: null
author: navistone
change_summary: Initial authoring (verified 2026-04-28). Sources — stripe.com/docs/webhooks, docs.github.com/webhooks, standardwebhooks.com.
raw_prose: |
  # Webhook Patterns

  ## Overview

  HMAC signing, replay protection, retry-with-backoff, and a dead-letter queue are the four non-negotiables for receiving webhooks from third parties (Stripe, GitHub, GitLab, Slack, Linear, Svix-managed senders). Skip any one and you ship either an injection vector or a silent data-loss surface.

  HMAC-SHA256 is the field consensus signing primitive (verified 2026-04-28). HMAC-SHA1 is legacy only — GitHub's `X-Hub-Signature` is deprecated; use `X-Hub-Signature-256`.

  ## When to use

  - Receiving webhooks from any third party (payment, VCS, chat, support tools).
  - Building your own webhook delivery system (sending events to customers).
  - Reviewing existing webhook code for the four non-negotiables.

  ## Authoritative sources (verified 2026-04-28)

  - Stripe webhook signatures: https://stripe.com/docs/webhooks/signatures
  - GitHub webhook validation: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
  - Standard Webhooks v1.0: https://www.standardwebhooks.com/

  Pairs with the `engineering` pack's `error-handling-patterns` for the operator surface around DLQs, and with `redis` if the dedup table or DLQ lives in Redis instead of Postgres.

fragments:
  - sequence: 1
    fragment_type: rationale
    content: ...   # see file; opens with skill name + 3 obvious-query keywords (R8)
  - sequence: 2
    fragment_type: setup
    content: ...   # standards landscape with verified date (R5), env vars, middleware order
  - sequence: 3
    fragment_type: execution
    content: ...   # HMAC verification — Stripe SDK helper + GitHub raw HMAC, both with imports (R2)
  - sequence: 4
    fragment_type: execution
    content: ...   # replay protection: timestamp tolerance + idempotency table
  - sequence: 5
    fragment_type: execution
    content: ...   # retry with full jitter + Retry-After
  - sequence: 6
    fragment_type: execution
    content: ...   # DLQ schema + retention + operator surface
  - sequence: 7
    fragment_type: example
    content: ...   # three-path handler: happy / signature-fail / duplicate (R4 case-space)
  - sequence: 8
    fragment_type: verification
    content: ...   # 13 mechanically-checkable items, half greppable (R3)
```

**Why this passes R1–R8**:
- R1: cites Stripe / GitHub / Standard Webhooks docs, all verified 2026-04-28.
- R2: every code block shows imports (`import express`, `import Stripe`, `import crypto`).
- R3: verification has 13 items, most expressed as `grep` commands or column checks.
- R4: end-to-end example walks three paths (happy / failed-sig / duplicate) explicitly.
- R5: every threshold is dated — `(verified 2026-04-28)`, `default 300s`, `30–90 days retention`.
- R6: `change_summary` says *"Initial authoring"* and lists actual sources.
- R7: no fabricated paths or domain terms.
- R8: rationale opens with "Webhook Patterns", "HMAC signing, replay protection, retry-with-backoff, dead-letter queue" — every obvious query keyword present.

### 4.2. Other batch-3 references

- `src/skillsmith/_packs/graphql/graphql-server-patterns.yaml` — protocol tier, framework-flavored content
- `src/skillsmith/_packs/observability/sentry-error-tracking.yaml` — cross-cutting tier, vendor SDK
- `src/skillsmith/_packs/websockets/websocket-scaling.yaml` — protocol tier, infra-shape content
- `src/skillsmith/_packs/engineering/feature-flags-openfeature.yaml` — foundation tier, standards-shape content

Read each in full before drafting in adjacent territory.

---

## 5. Fragment Type Taxonomy

Source: `src/skillsmith/ingest.py:50-52` and `:57-61` (thresholds), `fixtures/skill-qa-agent.md:88-104` (semantic guidance).

### 5.1. Allowed types

```python
_VALID_FRAGMENT_TYPES = {"setup", "execution", "verification", "example", "guardrail", "rationale"}
```

| Type | Purpose | Notes |
|---|---|---|
| `setup` | prerequisites, configuration, environment | env vars, install steps, imports, middleware order |
| `execution` | core task steps | the "how to do it" — most fragments are this |
| `verification` | mechanically-checkable post-conditions | every item must be a shell/assertion/binary observation (R3) |
| `example` | concrete illustrations | code samples covering the case-space (R4) |
| `guardrail` | constraints, things not to do, safety rules | "never use `===` for HMAC comparison" |
| `rationale` | why-explanations, not how | needs ≥3 obvious-query keywords (R8) |

The QA critic flags mislabeled types: an `execution` fragment that contains only "this is why we do X" must be relabeled `rationale`.

### 5.2. Word-count rules

```python
_FRAG_WORDS_HARD_MIN = 20      # below this → ingest hard-rejects
_FRAG_WORDS_WARN_MIN = 80      # below this → ingest warns; needs lexical anchoring
_FRAG_WORDS_WARN_MAX = 800     # above this → ingest warns; consider splitting
_FRAG_WORDS_HARD_MAX = 2000    # above this → ingest hard-rejects
```

Fragments under 80 words trigger: *"qwen3-embedding:0.6b is weak on small inputs — add lexical anchors or merge with neighbor."*

### 5.3. Type-diversity warning

`_lint` emits a warning when all fragments share the same type and there's more than one: *"diversify into setup/example/verification/guardrail/rationale."* Single-type skills retrieve poorly because they offer no shape.

### 5.4. Required-type warnings

- No `rationale` fragment → R8 warning: *"rationale anchors retrieval for 'why' queries; add one with ≥3 obvious-query keywords."*
- No `verification` fragment → R3 warning: *"verification items are contracts for downstream agents; add mechanically-checkable post-conditions."*

The 2026-04-28 corpus audit found 79% missing verification (368/468) and 66% missing rationale (309/468). New skills MUST include both unless the skill genuinely has no "why" or no externally-checkable surface (rare).

### 5.5. Contiguity

Every fragment's `content` must appear in `raw_prose` as a contiguous slice (whitespace normalized). Drift breaks BM25/full-text retrieval and the `_lint` pass rejects it.

### 5.6. Sequence + ordering

`sequence` is 1-indexed and monotonic within a skill. Convention: rationale → setup → execution(s) → example(s) → verification → guardrail. Not strictly enforced, but follows the natural reading order.

---

## 6. Rationale and Verification Block Formats

Both are `fragment_type` values, not separate top-level fields.

### 6.1. Good rationale block

From `webhook-patterns.yaml` fragment 1:

```yaml
- sequence: 1
  fragment_type: rationale
  content: |
    # Webhook Patterns

    HMAC signing, replay protection, retry-with-backoff, and a dead-letter queue are the four non-negotiables for receiving webhooks from third parties (Stripe, GitHub, GitLab, Slack, Linear, Svix-managed senders). Skip any one and you ship either an injection vector or a silent data-loss surface.

    HMAC-SHA256 is the field consensus signing primitive (verified 2026-04-28). HMAC-SHA1 is legacy only — GitHub's `X-Hub-Signature` is deprecated; use `X-Hub-Signature-256`.

    **Use this skill when:** receiving webhooks from any third party (payment, VCS, chat, support tools); building your own webhook delivery system; or reviewing existing webhook code for the four non-negotiables.
```

What's working:
- Skill name in the heading (lexical anchor 1)
- Every domain_tag appears in prose ("HMAC", "replay protection", "retry", "dead-letter queue", "Stripe", "GitHub")
- States the "non-negotiables" framing — gives a query like *"what must I get right about webhooks?"* a target
- States when to invoke — gives the retrieval orchestrator a phase signal

### 6.2. Bad rationale (rejected pattern)

```yaml
content: |
  This skill explains how to handle the technology in question
  using best practices and industry standards.
```

What's broken: no skill name, no specific terms, no version anchors, no when-to-use. R8 fails — the only query that surfaces this is one that already mentions "best practices industry standards", which doesn't match how anyone actually queries.

### 6.3. Good verification block

From `webhook-patterns.yaml` fragment 8:

```yaml
- sequence: 8
  fragment_type: verification
  content: |
    ## Verification

    For any webhook receiver, mechanical checks:

    - [ ] Signature verified against the **raw** request body (grep handler for `express.raw` or framework equivalent before the verify call).
    - [ ] Verification function uses `crypto.timingSafeEqual`, not `===` (grep for the receiver's verify helper).
    - [ ] Webhook secret loaded from environment, not hard-coded (`grep -rn "whsec_" src/` should return nothing).
    - [ ] Idempotency table exists and the handler inserts before doing work (`grep -n "INSERT INTO webhook_deliveries" src/`).
    - [ ] Duplicate-delivery path returns 200 (so the sender stops retrying), not 4xx.
    - [ ] Failed-signature path returns 400 or 401, never 200.
    - [ ] Failed-handler path returns 5xx so the sender retries...
```

Each item is greppable, observable, or a binary check. A downstream agent can mechanically run this list against a codebase.

### 6.4. Bad verification (rejected pattern)

```yaml
content: |
  - [ ] Webhooks are handled correctly
  - [ ] Security is in place
  - [ ] The system is robust
```

What's broken: nothing here is checkable. R3 fails — drop the items.

### 6.5. Authorship discipline (verification doubles as fabrication defense)

Verification fragments are also where claim provenance lives. A defensible verification fragment will, for any non-trivial assertion in the skill:

- Cite the primary source (URL or doc reference; date if version-relevant)
- Mark pattern-not-documented claims as such (so readers know they're idiom, not spec)
- Where feasible, include a small reproducible example that demonstrates the claim

If you can't write a check or cite a source for a claim, the claim shouldn't be in the skill.

---

## 7. Lint Behavior Reference

The QA gate runs three stages: deterministic structural lint → dedup → critic LLM. Source: `src/skillsmith/authoring/qa_gate.py`.

### 7.1. Stage 1 — Deterministic (mechanical) lint

Source: `src/skillsmith/ingest.py:_validate`, `_lint`, `src/skillsmith/lint_tags_mechanical.py`.

| Rule | What it checks | Verdict |
|---|---|---|
| Schema | required fields present, enum values valid | hard fail (validation error) |
| `system-empty` | system skill has empty `domain_tags` | hard fail if `skill_class=system` and tags non-empty |
| `tier-ceiling` | `len(domain_tags) <= soft_ceiling` for the resolved tier | warning |
| Hard cap | `len(domain_tags) <= 20` | hard fail |
| `R2` (mechanical) | tag stem overlaps title stem | `verdict="redundant_with_title"` (warning, folded into blocking_issues if combined with semantic) |
| `R3-stem` | pairwise tag stem overlap | `verdict="synonym_of:<other>"` |
| `W1` | workflow skill has ≥1 marker | `verdict="missing_position_marker"` (hard fail) |
| Fragment word counts | `20 ≤ words ≤ 2000` | hard fail; warns at 80 / 800 |
| Contiguity | each fragment is a slice of `raw_prose` | hard fail (`drift breaks BM25/full-text retrieval`) |
| Type validity | `fragment_type ∈ _VALID_FRAGMENT_TYPES` | hard fail |
| Type diversity | not all fragments same type when len>1 | warning |
| Required types | rationale + verification present | warning |

### 7.2. Stage 2 — Dedup

Source: `src/skillsmith/authoring/dedup.py`, `src/skillsmith/authoring/qa_gate.py:run_dedup`.

Per-fragment cosine similarity against the active corpus.

- Score > 0.92 → **hard duplicate** → skill rejected (operator can `--force`)
- 0.80 ≤ score ≤ 0.92 → **soft duplicate** → passed to the critic for judgment
- Score < 0.80 → ignored

### 7.3. Stage 3 — Critic (LLM)

Source: `fixtures/skill-qa-agent.md` (system prompt), `src/skillsmith/authoring/qa_gate.py:run_critic`.

Output is a JSON object — `CriticVerdict`:

```python
@dataclass
class CriticVerdict:
    verdict: str                          # "approve" | "revise" | "reject"
    summary: str                          # one-sentence rationale
    blocking_issues: list[str]            # empty iff verdict="approve"
    per_fragment: list[dict[str, Any]]    # {"sequence": int, "issue": null | str}
    dedup_decisions: list[dict[str, Any]] # {"near_dup_skill_id", "score", "distinct", "reason"}
    suggested_edits: str                  # free-form guidance
    tag_verdicts: list[dict[str, Any]]    # see §7.4
    prompt_version: str                   # echoed from the prompt's version pin
```

Effectiveness rubric the critic applies (from `skill-qa-agent.md:82-141`):

1. **Self-contained fragments** — each retrievable alone
2. **Fragment-type accuracy** — type matches content
3. **Category-fit** — `category` matches actual content vs canonical vocabulary
4. **Tag relevance** — tags surface fragments for the right reason
5. **Size sanity** — flag <40 words as under-fragmented, >400 as under-split
6. **Non-redundancy** — for each soft dedup hit, decide distinct vs duplicate
7. **Source fidelity** — fragment content is verbatim from `raw_prose`

### 7.4. Tag verdicts (semantic lint)

From `lint_tags_semantic.py:build_semantic_lint_block` — appended to the critic's user prompt.

```json
[
  {"tag": "<tag>", "rule": "R1|R3-syn|R4",
   "verdict": "pass|not_queryable|synonym_of:<other>|off_intent",
   "detail": "<explanation>"}
]
```

| Verdict | Meaning | Typical fix |
|---|---|---|
| `pass` | tag is acceptable | none |
| `not_queryable` | tag is internal jargon, not how anyone would search | replace with a term real queries use |
| `synonym_of:<other>` | duplicates another tag in the same skill | remove the redundant one |
| `off_intent` | tag promises content the skill doesn't actually deliver | remove the tag, or add the content |
| `missing_position_marker` | (mechanical, workflow only) no W1 marker | add a `WORKFLOW_POSITION_MARKERS` value |
| `redundant_with_title` | (mechanical) tag stem overlaps title | drop the tag |
| `over_ceiling` | (mechanical) tags exceed tier soft_ceiling | remove low-signal tags |
| `system_has_tags` | (mechanical) system skill has non-empty `domain_tags` | set to `[]` |

Non-pass `tag_verdicts` are folded into `blocking_issues` automatically (`qa_gate.py:_parse_critic_response`).

### 7.5. Verdict routing

- **approve** → moves draft to `pending-review/`
- **revise** → moves to `pending-revision/` with sibling `.qa.md` report; bounce counter +1
- **reject** → moves to `rejected/`
- **bounce_budget exceeded** (default 3) → next revise becomes **needs-human**

---

## 8. Common Authoring Pitfalls

Drawn from `docs/skill-review-history/2026-04-28-batch-2-stack-foundations.md`, `2026-04-28-mattpocock-import.md`, `2026-04-28-corpus-yaml-quality-review.md`.

### 8.1. From batch-2 (fast-moving APIs)

| Pitfall | Skill | Fix |
|---|---|---|
| Mocha tsx loader via `.mocharc.cjs` `loader:` field | mocha-chai-sinon | Use `--import tsx` on the script line |
| Soft-delete extension overriding only read-list methods | prisma-orm-patterns | Cover the full client method surface or document gaps |
| Tool-loop examples without a `MAX_TURNS` cap | claude-api-patterns | Always cap |
| Mongo shell syntax in Node-driver examples | mongodb-patterns | Driver wants `new Decimal128('19.99')`, not `NumberDecimal('19.99')` |
| sysctl-level fixes for app-level problems | podman-rootless | Prefer `setcap` or reverse proxy |
| PgBouncer pools without `directUrl` for migrations | postgres-deep-patterns | `migrate deploy` fails through transaction-mode pooling |

### 8.2. From mattpocock import (R6/R7 violations)

- **Over-authoring labelled "imported"** — 4-line upstream source expanded to 159-line YAML with `change_summary: imported from`. Use *"scaffold by skillsmith around upstream prose preserved in fragment N"* when most content is yours.
- **Fabricated domain terms presented as canonical** — `payments adapter`, `checkout aggregate`, `apps/api/src/orders/finalize.ts` invented as if from a known glossary. Prefix with *"Illustrative — not from a real codebase:"* or use schematic names.
- **Rationale missing the obvious query keyword** — zoom-out's rationale never said *"architecture"* or *"architectural context"*.

### 8.3. From corpus audit (structural)

- **No verification (79%)** — most skills shipped with no R3 contract. Adding a verification fragment is the single highest-leverage authoring move.
- **No rationale (66%)** — most skills have no R8 anchor for "why" queries.
- **Fragments under 80 words (93%)** — ubiquitous; either expand with lexical anchors or merge with neighbor.
- **Tag synonyms within the same skill** — `signing` + `hmac` + `signature` — pick one surface form per concept.
- **Skills covering multiple intents** — when a skill's tags span unrelated topics, split into separate skills.

---

## 9. Authoring Workflow

### 9.1. File layout

Skills live at `src/skillsmith/_packs/<pack-name>/<skill-id>.yaml`. Every pack directory has a sibling `pack.yaml`. The skill's `tier` field is resolved via `skill_tier.resolve_skill_tier()` walking up to that `pack.yaml`.

Naming: `skill_id` is kebab-case, file name is `<skill_id>.yaml`. `pack.yaml`'s `skills:` inventory lists every skill file with `fragment_count` for the inventory check.

### 9.2. End-to-end flow

```
                 Author SKILL.md (source markdown)
                              │
                              ▼
            skill-authoring-agent.md (LLM transforms → review YAML)
                              │
                              ▼
             skill-source/pending-qa/<skill_id>.yaml
                              │
                              ▼ (operator runs qa_gate)
            ┌───────────────────────────────────────────┐
            │ Stage 1: deterministic structural lint    │
            │ Stage 2: dedup (semantic)                 │
            │ Stage 3: critic LLM                       │
            └───────────────────────────────────────────┘
                              │
            ┌─────────────────┼──────────────────┐
            ▼                 ▼                  ▼
       pending-review/   pending-revision/   rejected/
       (approve)         (revise; loop)     (reject)
                              │
                              ▼
            (operator) → ingest → LadybugDB + DuckDB embeddings
```

### 9.3. CLI entry points

```bash
# Run QA gate on all drafts in pending-qa/
python -m skillsmith.authoring qa_gate

# Ingest a single approved YAML
python -m skillsmith.ingest path/to/skill.yaml
python -m skillsmith.ingest path/to/skill.yaml --force      # overwrite existing skill_id
python -m skillsmith.ingest path/to/skill.yaml --strict     # warnings → errors
python -m skillsmith.ingest path/to/skill.yaml --yes        # skip confirmation

# Batch-ingest a directory
python -m skillsmith.ingest path/to/yaml-dir/

# Exit codes: 0 success, 2 validation error, 4 duplicate
```

### 9.4. Iteration loop

When the QA gate emits `revise`:

1. Read the sibling `<skill_id>.qa.md` report — it carries `summary`, `blocking_issues`, `per_fragment`, `tag_verdicts`, `suggested_edits`.
2. Address every entry in `blocking_issues`. Line-level edits only — resist redesigning.
3. Move the YAML back to `pending-qa/` and re-run `qa_gate`.
4. After 3 bounces (default `bounce_budget`), the next revise escalates to `needs-human/`. If you're hitting the bounce budget, the source skill is probably mis-shaped — go back to `SKILL.md` and rethink.

### 9.5. Local sanity checks before submitting

```bash
# Type + lint clean
ruff check . && ruff format --check . && uv run pyright

# Tests still green
pytest -q

# Validate without ingesting (dry-run via _lint internal)
python -c "from skillsmith.ingest import _load_yaml, _lint, _validate; \
           r = _load_yaml('path/to/skill.yaml'); \
           print('errors:', _validate(r)); \
           print('warnings:', _lint(r))"
```

---

## 10. Source Discipline and Fabrication Prevention

Skills that pass structural lint while being factually wrong are worse than missing skills — they pollute the corpus with confident misinformation. The lint cannot catch fabrication; only source discipline can.

### 10.1. Per-tier canonical sources

For each tier, prefer these primary sources before drafting:

| Tier | Canonical sources |
|---|---|
| `language` | language specs (python.org/doc, typescriptlang.org/docs, go.dev/ref/spec, doc.rust-lang.org/reference) |
| `framework` | official framework docs, framework's GitHub repo for examples, maintainer-authored migration guides for version-specific content |
| `store` | official database docs at the version the pack targets, official query planner docs, official driver/ORM docs |
| `protocol` | RFCs (cite by RFC number), W3C specs, IETF documents; for security protocols, also OWASP guidance |
| `platform` | cloud provider docs, IaC tool docs (terraform.io/docs, opentofu.org/docs), container runtime docs (podman.io, docs.docker.com) |
| `tooling` | tool's own docs + GitHub repo for current usage |
| `cross-cutting` | OWASP for security, W3C for accessibility; observability vendor docs only as secondary after standards |
| `domain` | depends on subject — for ML/LLM packs, papers + official model docs; for industry domains, official regulatory documents (HIPAA, PCI) |
| `workflow` | lower fabrication risk; established practice references (Google SRE book for incident response) where applicable |
| `foundation` | lower fabrication risk; cite where canonical sources exist |

### 10.2. Source authority hierarchy

1. **Primary** — official documentation, language specs, RFCs, the maintainer's repo.
2. **Maintainer-adjacent (last 12–18 months)** — official blog posts, conference talks by maintainers, project's own examples.
3. **Synthesized patterns from training data** — only acceptable for genuinely stable cross-cutting concerns. Must be marked as *"common pattern, not officially documented"* when used.

### 10.3. What sources NOT to use

- Stack Overflow as authoritative (acceptable as a hint, not a citation)
- Medium articles or random blog posts unless authored by a known maintainer
- AI-generated content from any source
- Tutorials or courses without a clear authoritative origin
- Anything older than 2 years for fast-moving technologies (frontend frameworks, AI/ML, cloud services)

### 10.4. Required authoring discipline

Before drafting any skill, the agent must:

1. Identify the canonical source for the technology or pattern in question.
2. Read the relevant section of that source.
3. Cite it in the skill's verification fragment or `change_summary` — what claim is supported by what source, with date.
4. If a claim cannot be supported by a primary source, find a maintainer-adjacent source from the last 18 months OR mark the claim *"common pattern, not officially documented"* and keep it conservative.
5. Not author claims based on training data alone for version-specific behavior, recently-changed APIs, or "best practice" recommendations — those require source verification.

### 10.5. Tier-by-tier fabrication risk profile

| Risk | Tiers | Authoring discipline |
|---|---|---|
| **High** | `language`, `framework`, `store`, `protocol`, most `domain` | Fetch current docs (R1). Quote signatures. Date-stamp version claims (R5). |
| **Medium-high** | `tooling`, `platform` | Version churn but more pattern-stable. Still verify CLI flags and config schemas against current docs. |
| **Medium** | `cross-cutting` | Patterns more stable but specific implementations vary. Cite OWASP/W3C for the standards layer. |
| **Low** | `foundation`, `workflow` | Mostly stable cross-cutting concerns or process content. Still need lexical-anchor discipline (R8). |

The model selection guide routes high-risk tiers to Opus 4.7. This section reinforces *why* and gives the agent the source-discipline tools to use that quality budget well.

### 10.6. Verification harness (current state)

As of 2026-04-30, skillsmith has **no automated harness that runs verification examples against real systems**. Verification fragments are checked structurally (R3 — items must be greppable/assertable) but not executed.

This is a known v1 gap. For fact-dependent packs (`store`, `framework`, `protocol`), the strongest defense remains:

- Date-stamp every numeric claim (R5)
- Cite the primary source per claim in `change_summary` or the verification fragment
- Include reproducible code that the operator can run before merging
- Manual operator verification of high-risk skills before ingest

---

## Appendix A — Quick reference card

```
Required top-level fields:
  skill_type, skill_id, canonical_name, category, skill_class,
  domain_tags, always_apply, author, change_summary, raw_prose, fragments

skill_class:    domain | system | workflow
fragment_type:  setup | execution | verification | example | guardrail | rationale
domain category:    engineering | ops | review | design | tooling | quality
system category:    governance | operational | tooling | safety | quality | observability
phase_scope:    design | build | review

Word counts:    20 (hard) / 80 (warn) ≤ words ≤ 800 (warn) / 2000 (hard)
Tag cap:        ≤ 20 hard, ≤ tier soft_ceiling soft

Hard rules:
  - System skills: skill_id starts "sys-", domain_tags is []
  - Workflow skills: ≥1 WORKFLOW_POSITION_MARKERS tag (W1)
  - Every fragment.content is a contiguous slice of raw_prose
  - System skills declare applicability: always_apply OR phase_scope OR category_scope

Authoring rules (fixtures/skill-authoring-guidelines.md):
  R1: Fetch authoritative docs for fast-moving APIs
  R2: Show import once per non-stdlib name
  R3: Verification items must be mechanically checkable
  R4: Examples cover the case-space, not just happy path
  R5: Date-stamp version-specific claims
  R6: change_summary labels authorship honestly
  R7: Flag fabricated examples ("Illustrative — not from a real codebase:")
  R8: Rationale fragments include ≥3 obvious-query keywords
  W1: Workflow skills carry a position marker
```

## Appendix B — File map

| Concern | Path |
|---|---|
| YAML schema (dataclasses) | `src/skillsmith/reads/models.py`, `src/skillsmith/ingest.py:103-124` |
| Validation | `src/skillsmith/ingest.py:_validate` (line 480) |
| Lint warnings | `src/skillsmith/ingest.py:_lint` (line 620) |
| Mechanical tag lint | `src/skillsmith/lint_tags_mechanical.py` |
| Semantic tag lint | `src/skillsmith/lint_tags_semantic.py` |
| QA gate pipeline | `src/skillsmith/authoring/qa_gate.py` |
| Critic system prompt | `fixtures/skill-qa-agent.md` |
| Authoring contract | `fixtures/skill-authoring-guidelines.md` |
| Pack manifest spec | `docs/PACK-AUTHORING.md` |
| Pack tier resolver | `src/skillsmith/skill_tier.py` |
| Pack tier registry | `src/skillsmith/install/subcommands/install_pack.py:_VALID_PACK_TIERS` |
| Tag policy by tier | `src/skillsmith/ingest.py:TAG_POLICY_BY_TIER` (line 82) |
| Workflow markers | `src/skillsmith/ingest.py:WORKFLOW_POSITION_MARKERS` (line 63) |
| Gold-standard skills | `src/skillsmith/_packs/{webhooks,graphql,observability,websockets,engineering}/*.yaml` |
| Review history | `docs/skill-review-history/` |
| Corpus audit | `docs/skill-review-history/2026-04-28-corpus-yaml-quality-review.md` |
