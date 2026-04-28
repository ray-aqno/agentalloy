# Skill Authoring Guidelines

Quality contract for writing a NEW skill source from scratch. Applies BEFORE
`skill-authoring-agent.md` (which only transforms source → review YAML).

Rules are derived from adversarial review of shipped batches; each cites the
shipped failure that produced it. Treat as a checklist — if you can't satisfy a
rule, drop the example or the claim, don't paper over it.

Reviews informing these rules:
- `docs/skill-review-history/2026-04-28-batch-2-stack-foundations.md` (R1–R5: authoring fresh content against fast-moving APIs)
- `docs/skill-review-history/2026-04-28-mattpocock-import.md` (R6–R8: importing third-party content + retrieval tuning)

---

## R1 — Fetch authoritative docs before authoring against fast-moving APIs

For frameworks <2 years old, ML/agent SDKs, and vendor SDKs (Anthropic, Prisma,
OTel, mongo Node driver, mocha+tsx loaders), fetch current docs via
`ctx_fetch_and_index` BEFORE writing examples. Quote them when the example
uses a non-trivial signature.

Training-data knowledge is allowed to be ~6 months stale on these APIs and
routinely is. Batch 2 shipped wrong Prisma generator name, Mongo `Decimal128`
shell-vs-driver syntax, mocha `loader:` field, and OTel
`resourceFromAttributes` because of stale recall.

## R2 — Every non-stdlib name in a code block must show its `import` once

If a block references `Prisma.Decimal`, `Decimal128`, `Anthropic.Tool`,
`PrismaClientKnownRequestError`, etc., at least one block in the same skill
must show the `import` line. Examples without imports compile in nobody's
editor.

## R3 — Verification fragments are contracts; every item must be mechanically checkable

A verification item is a post-condition a downstream agent will check. Each
item must be expressible as a one-line shell command, a single assertion, or a
binary observation. Vague items ("good practices followed", "config is
sensible") and unverified claims ("env-var change requires server restart" —
wrong; Vite watches `.env*`) do not survive this rule.

If you can't write the check, drop the item.

## R4 — Examples must cover the case-space, not just the happy path

Two failure modes, one rule:

- **Surface coverage.** When an example claims to cover a state machine, an
  enum, or a method set, enumerate every case and comment why each is or isn't
  handled. A soft-delete extension that overrides `findMany` + `findFirst` but
  skips `findUnique`, `count`, `update.where`, `deleteMany` leaks deleted
  rows — a correctness bug, not a style nit.
- **Edge trace.** Before committing any example, walk one realistic edge case
  through it mentally. Most batch-2 issues were happy-path examples that
  silently failed on the rare-but-real case (runaway tool loops, OFFSET-based
  pagination at scale, async assertions that race the promise).

See "Anti-patterns observed" below for shipped instances.

## R5 — Date-stamp version-specific or minimum-value claims

Numeric thresholds, version requirements, and minimums change. When you write
"cache prefix ≥ 4096 tokens for Opus", "INCLUDE syntax requires Postgres 11+",
"`resourceFromAttributes` needs `@opentelemetry/resources` v1.27+", append
`(verified YYYY-MM-DD)` inline or list it in a footer `## Verified` block.

A reader six months out needs to know whether to trust the number or re-check.
"I don't know — go check" beats a confident wrong number.

## R6 — Imports must label authorship honestly

If `raw_prose` is verbatim from upstream, `change_summary` says
`imported verbatim from <upstream-path>`.

If you authored scaffolding (rationale, examples, guardrails) around upstream
prose, `change_summary` says
`scaffold by skillsmith around upstream prose preserved in fragment <N>`.

Never write "imported" when you authored most of the content. Batch-import of
mattpocock/skills shipped 4-line sources expanded to 159-line YAMLs labelled
"imported" — closer to "inspired by." Readers expecting upstream voice got a
different one.

## R7 — Fabricated examples must be flagged or replaced

If an example names a file path, function, domain term, or API that doesn't
exist in any real codebase, prefix with
`Illustrative — not from a real codebase:` or replace with a less specific
schematic.

zoom-out shipped `apps/api/src/orders/finalize.ts`, `checkout aggregate`,
`payments adapter`, `order projection` as if from a known glossary. They
weren't. Made-up domain terms presented as canonical mislead readers and the
embedder anchors retrieval on fictional vocabulary.

## R8 — Rationale fragments need lexical anchors for the obvious query

A short rationale fragment without the keywords a real query would use is
under-discriminative for `qwen3-embedding:0.6b`. Each rationale fragment must
include ≥3 of the obvious query terms for the skill it explains.

For zoom-out: "architecture", "architectural context", "system map", "module
boundaries". If your rationale doesn't contain those words, retrieval on
"how do I get higher-level architectural context?" won't surface it.

Pair this rule with the fragment length floor (≥80 words) — short fragments
need explicit lexical anchoring to compensate for the embedder's weakness on
small inputs.

---

## Process for a new batch

1. Fetch authoritative docs for each skill (R1, R5).
2. Author the source. Apply R2, R3, R4 as you write; if importing, R6–R7.
3. Self-review verification fragments against R3 and rationale fragments
   against R8.
4. Dispatch an independent critic with this doc + the latest review history.
5. Single revision pass. Line-level fixes only — resist redesigns.
6. Hand off to `skill-authoring-agent.md` for source → review YAML.

---

## Anti-patterns observed (do not repeat)

Running ledger. Append after each batch's review.

- **Mocha tsx loader via `.mocharc.cjs` `loader:` field.** Use `--import tsx`
  on the script line; document `c8` for coverage. (batch 2, mocha-chai-sinon)
- **Soft-delete extension overriding only read-list methods.** Cover the full
  client method surface or document the gaps. (batch 2, prisma-orm-patterns)
- **Tool-loop examples without a `MAX_TURNS` cap.** Always cap.
  (batch 2, claude-api-patterns)
- **Mongo shell syntax in Node-driver examples.** `NumberDecimal('19.99')` is
  shell; driver wants `new Decimal128('19.99')`. (batch 2, mongodb-patterns)
- **sysctl-level fixes for app-level problems.** Prefer `setcap` or a reverse
  proxy over `net.ipv4.ip_unprivileged_port_start`. (batch 2, podman-rootless)
- **Connection pools through PgBouncer without `directUrl` for migrations.**
  `migrate deploy` fails through transaction-mode pooling. (batch 2,
  postgres-deep-patterns)
- **Over-authoring labelled as "imported".** 4-line upstream source expanded
  to 159-line YAML with the original `imported from` change_summary.
  (mattpocock import, grill-me, zoom-out)
- **Fabricated domain terms presented as canonical.** `payments adapter`,
  `checkout aggregate`, `apps/api/src/orders/finalize.ts` — invented file
  paths and glossary terms in a worked example. (mattpocock import, zoom-out)
- **Rationale fragment missing the obvious query keyword.** zoom-out's
  rationale never says "architecture" or "architectural context" — the words
  a real query uses. (mattpocock import, zoom-out)
