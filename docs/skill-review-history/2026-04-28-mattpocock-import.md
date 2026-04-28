# Mattpocock Import — Adversarial Review

Date: 2026-04-28
Scope: 3 new YAMLs (caveman, grill-me, zoom-out) + 3 edited YAMLs (TDD, debugging-strategies, planning-and-task-breakdown) + 2 manifests.
Method: source SKILL.md compared to authored YAML, schema spot-check, retrieval-shape inspection, manifest reconciliation.

---

## 1. Severity-Ranked Findings

### Critical

**C1. Faithfulness drift — fragment 8 of TDD silently drops a load-bearing sentence from raw_prose.**
File: `src/skillsmith/_packs/core/test-driven-development.yaml:398` (raw_prose) vs `:821` (fragment 8).
raw_prose contains: *"Each test responds to what you learned from the previous cycle. Because you just wrote the code, you know exactly which behavior matters and how to verify it."* Fragment 8 truncates after "previous cycle." That second clause is the entire causal argument for tracer-bullet TDD — it's the *why*. Fragment 8 will retrieve as "do vertical slices because… reasons." raw_prose ↔ fragment drift will also fail any future "fragments must be contiguous slice of raw_prose" lint.
Fix: append the dropped sentence to fragment 8 verbatim from raw_prose.

**C2. raw_prose drift in debugging-strategies and planning — fragments diverge silently.**
Files: `src/skillsmith/_packs/core/debugging-strategies.yaml` (fragments 16, 17 added at :230 and :288, raw_prose unchanged at :20), `src/skillsmith/_packs/core/planning-and-task-breakdown.yaml` (fragment 14 added at :356, raw_prose unchanged at :17).
You explicitly chose not to extend raw_prose. Effect: hybrid retrieval that scores against raw_prose (BM25 / full-text on the canonical body) will never see the new content; only the fragment-level path can surface it. If anything in skillsmith re-renders the skill from raw_prose (export, prose-mode prompt assembly, or future re-fragmentation), the new content vanishes. Pack manifest fragment_count will agree, but the artefact is internally inconsistent.
Fix: either extend raw_prose with the new sections (preferred — same content, identical wording), or document the policy "fragments may extend raw_prose; raw_prose is the snapshot at time of seed authoring" in PACK-AUTHORING.md and add a ratification field per skill (e.g. `prose_authoritative: false`).

**C3. Pre-existing chunking pollution in debugging-strategies fragments 3–11 (not your bug, but the new fragments inherit the file).**
File: `src/skillsmith/_packs/core/debugging-strategies.yaml:95, :98, :101, :104, :149, :155, :158`. Fragments end mid-stream with stray `\`\`\`` closers and `### Phase 2: Gather Information\n\n\`\`\`markdown` openers — the previous chunker split inside fenced markdown blocks. Embeddings will be dominated by `\`\`\`markdown` tokens. Your additions (16, 17) are clean, so fragment 16/17 will out-retrieve fragments 3–11 for almost any debugging query. That's good for your content, bad for the skill — half the skill is currently unretrievable.
Fix: out of scope for this PR but flag as follow-up. Re-fragment 1–15 from raw_prose in a separate change.

### Important

**I1. grill-me / zoom-out: massive over-expansion vs source.**
Files: `src/skillsmith/_packs/core/grill-me.yaml` (raw_prose 47 lines) vs `/tmp/mattpocock-skills/skills/productivity/grill-me/SKILL.md` (4 lines of prose). zoom-out: `src/skillsmith/_packs/engineering/zoom-out.yaml` (~63 lines) vs source (1 line of prose). You added the "Why this works", "Rules of cadence", "Anti-patterns", a fully invented worked example (orders-saga, `apps/api/src/orders/finalize.ts`), and the "boundary breaks if you change the return shape" claim. None of that is in the source. The example is plausible-sounding but fabricated.
Impact: change_summary says "imported from mattpocock/skills" — readers will expect Matt wrote it. He didn't. This is closer to "inspired by" than "imported from."
Fix: either (a) shrink to faithful import — keep only what's in source plus minimal scaffolding, mark embellishments clearly; or (b) keep the embellishments but rewrite change_summary to *"adapted from mattpocock/skills MIT — original prose preserved verbatim in fragment N; surrounding rationale, examples, and guardrails authored by skillsmith"*. Option (b) is honest and probably what you want.

**I2. caveman fragment 1 voice mismatch — adds hedging Matt explicitly forbids.**
File: `src/skillsmith/_packs/core/caveman.yaml:48-61`. Source says: *"Respond terse like smart caveman. All technical substance stay. Only fluff die."* You moved that to "Core principle" and front-loaded the fragment with "Ultra-compressed response mode. Drops articles, filler, pleasantries, and hedging while preserving every technical detail. Typical token reduction ~75% versus default prose." That paragraph is itself the prose Matt is telling you to stop writing. The skill is about tone; the fragment violates the tone. If a retrieval call surfaces this fragment to the model, the *first thing* the model reads is verbose meta-prose. The lede should be the caveman directive, not the explainer.
Fix: invert fragment 1 — open with the directive ("Respond terse like smart caveman…"), demote the metadata to a trailing line.

**I3. zoom-out fabricated example claims domain knowledge it doesn't have.**
File: `src/skillsmith/_packs/engineering/zoom-out.yaml:118-150`. The "good response" names *order materialisation*, *checkout aggregate*, *payments adapter*, *order projection* as if these were real terms in a known glossary. They aren't — there is no `apps/api/src/orders/finalize.ts` in any source. A user reading this fragment may parse the made-up domain terms as canonical. If the example is meant to be illustrative, it should be flagged as fictional ("Hypothetical example:") or grounded in a real glossary the corpus ships.
Fix: prefix with "Illustrative — not from a real codebase:" or replace with a less specific schematic.

**I4. grill-me Q1 example is dated/wrong.**
File: `src/skillsmith/_packs/core/grill-me.yaml:117-124`. "Recommended: single endpoint with an `event` field — matches Stripe/GitHub patterns." Stripe sends one event type per webhook delivery (`type: "invoice.paid"`) but each event type is on the *same* endpoint URL — so the recommendation is fine, but the framing "single endpoint with an event field in the payload" misrepresents how Stripe/GitHub actually structure it (they send one event per POST; the URL is shared). A skill teaching "interview the operator with recommended answers" cannot ship recommendations whose justification is shaky.
Fix: replace with a less load-bearing example, or drop the Stripe/GitHub appeal-to-authority.

**I5. Missing THIRD_PARTY_LICENSES.md.**
No file at `THIRD_PARTY_LICENSES.md` or `docs/THIRD_PARTY_LICENSES.md`. You imported MIT-licensed content from mattpocock/skills into 6 YAMLs; MIT requires you to retain the copyright notice and license text in distributions. change_summary lines mention MIT and the upstream path but that is not the same as ship­ping the license. Pack `license: MIT` in `pack.yaml:8` is the *pack's* license, not an attribution of the upstream.
Fix: create `THIRD_PARTY_LICENSES.md` at repo root; include Matt's copyright + MIT text; list each imported skill with its source path. Reference it from each pack.yaml or from the README.

**I6. caveman category=tooling is a stretch.**
File: `src/skillsmith/_packs/core/caveman.yaml:4`. caveman is a *response style* directive — closer to a meta-instruction than a tool. Allowed categories are design/engineering/ops/quality/review/tooling. None fit cleanly. `tooling` (alongside `using-agent-skills`) is defensible but the closest analogue in the existing corpus would be a "communication" or "interaction" category that doesn't exist.
Fix: keep `tooling` and accept the imperfect fit, or open a separate question about adding a `meta` / `interaction` category. Not blocking.

### Minor

**M1. Mixed YAML scalar styles within a single file.**
caveman.yaml uses double-quoted folded strings for raw_prose (`:19`) but single-quoted block-folded for fragments. grill-me, zoom-out, planning use single-quoted folded. test-driven-development uses literal block (`|`) at `:13` and inside fragments (`:426`). debugging-strategies uses double-quoted folded for raw_prose (`:20`) and a mix in fragments. This loads correctly (Python yaml.safe_load passes for all six) but produces visually inconsistent diffs and harder review. Authoring guidance should pick one default.
Fix: standardise on literal block (`|`) for any content that contains markdown — preserves whitespace, no quote-doubling, diffs cleanly. Reserve folded/quoted for short single-line strings.

**M2. caveman.yaml raw_prose has \\n explosion.**
File: `src/skillsmith/_packs/core/caveman.yaml:19-44`. Encoded as one giant double-quoted folded scalar with `\n` escapes everywhere. Visually unreviewable. Fragment versions are fine.
Fix: re-emit raw_prose with `|` block scalar, same as test-driven-development.yaml does at line 13.

**M3. zoom-out fragment 1 is short (~95 words, ~700 chars). Probably below the embedding sweet spot.**
qwen3-embedding:0.6b will produce a vector but discriminative power on short rationale fragments is poor. Compare to caveman fragment 1 (~80 words) and grill-me fragment 1 (~95 words). All three new rationale fragments are at the low end. A user query like "how do I get higher-level architectural context?" may not strongly retrieve any of them — the keyword "architectural" doesn't appear in zoom-out fragment 1.
Fix: add the words "architecture", "architectural context", "system map" to fragment 1 of zoom-out. Same for the other two.

**M4. grill-me fragment 3 deictic "Operator answers one, the others get lost" depends on prior context.**
File: `src/skillsmith/_packs/core/grill-me.yaml:144-145`. Fragment 4 (anti-patterns) opens "Bundling questions. 'What about auth, retries, and signing?'" — fine in context, but if retrieved alone the reader has to back-infer the framing.
Fix: lead with "When grilling a plan, do not bundle questions." Self-contained.

**M5. test-driven-development fragment 8 final checklist mirrors fragment 7 verification checklist.**
File: `:797-808` (frag 7) and `:840-845` (frag 8). Both end with checklists about tests describing behaviour, public interface, surviving refactors. They're not literal duplicates but they will compete for retrieval on "tdd checklist" queries.
Fix: rename frag 8 checklist to "Per-cycle tracer-bullet checklist" and lead with "After each red→green cycle:" so the embedding distinguishes from the post-implementation verification.

**M6. planning fragment 14 issue body template uses fenced code block inside single-quoted YAML.**
File: `src/skillsmith/_packs/core/planning-and-task-breakdown.yaml:399-429`. Loads OK but the triple-backtick + apostrophes inside (`don't`, `can't`) make the single-quoted folded form fragile. Already escaped correctly (none in this fragment), but it's the kind of payload that wants `|` block scalar.
Fix: switch to literal block.

**M7. caveman.yaml change_summary describes content faithfully but lacks upstream-path field.**
File: `:16-18`. Mentions "(productivity/caveman)" inline. Other skills in the corpus don't have an `upstream` field at all, so this isn't drift, but if you're going to import upstream skills systematically, a structured `upstream:` key (not free-text) would let you grep "all imports from mattpocock" later.
Fix: add optional `upstream:` field to schema, populate it for the 6 affected skills, document in PACK-AUTHORING.md.

### Nit

**N1. caveman raw_prose at :22-23** uses "or invokes /caveman." but fragment 1 at :57 uses "or invokes /caveman." — fine, consistent. Skip.

**N2. zoom-out source has `disable-model-invocation: true`** in its frontmatter. The skillsmith schema has no equivalent (`always_apply: false` is the closest). Source is signalling "do not auto-invoke; user must explicitly trigger." Worth noting but not actionable today.

**N3. grill-me fragment 4 (`:142-159`)** — six anti-patterns listed; the last two ("Stopping early" / "Stopping late") are good but were authored by you, not in source. See I1.

**N4. Manifest semver:** core 1.0.0 → 1.1.0 with two new skills + edits is correct (additive = MINOR). engineering 1.0.0 → 1.1.0 with one new skill, same. Fine.

**N5. test-driven-development.yaml fragment indentation** (4-space `    - sequence:`) is inconsistent with the rest of the corpus (which uses 0-space `- sequence:`). Loads fine; not author-introduced. Pre-existing.

---

## 2. Per-File Scorecard

**caveman.yaml** — Solid structure, good fragment partition; voice issue (I2) is the only real problem. raw_prose unreadable but functional (M2).
- Strengths: 5 fragments, all distinct types (rationale/setup/execution/example/guardrail), self-contained, faithful to source.
- Weaknesses: fragment 1 lede contradicts the skill's own directive (I2); raw_prose stylistic mess (M2); imperfect category (I6).

**grill-me.yaml** — Over-authored. Source is 4 lines; you produced 159. Useful expansion but mislabelled as "imported."
- Strengths: cadence rules cleanly extracted; example is well-shaped.
- Weaknesses: change_summary misrepresents authorship (I1); Stripe/GitHub claim shaky (I4); fragment 4 deictic (M4).

**zoom-out.yaml** — Same over-authoring problem as grill-me, plus a fabricated worked example.
- Strengths: clear use-when triggers; clean prompt body in fragment 2.
- Weaknesses: example fabricates domain terms (I3); change_summary misrepresents authorship (I1); rationale fragment lacks the keywords a real query would use (M3).

**test-driven-development.yaml** — Fragment 8 is good content, drifts from raw_prose in one sentence.
- Strengths: voice matches existing fragments; vertical-slice argument is the right addition.
- Weaknesses: dropped sentence (C1); checklist competes with frag 7 (M5).

**debugging-strategies.yaml** — Fragments 16 and 17 are genuinely strong content; the file they live in is a chunker disaster (C3). raw_prose drift (C2).
- Strengths: fragment 16 is the best fragment in the file; the "build a feedback loop first" lede is exactly what the embedder needs.
- Weaknesses: raw_prose not extended (C2); inherits a polluted file (C3).

**planning-and-task-breakdown.yaml** — Fragment 14 clean; raw_prose drift again.
- Strengths: HITL/AFK framing is novel and useful; issue template is concrete.
- Weaknesses: raw_prose not extended (C2); fenced block in single-quoted YAML is fragile (M6).

---

## 3. Authoring Rules to Add to PACK-AUTHORING.md

Short, actionable additions:

1. **raw_prose is the canonical body.** Fragments must be contiguous slices of raw_prose. If you extend fragments, extend raw_prose with the same wording in the same order. Lint: assert each fragment's content is a substring of raw_prose (modulo whitespace).
2. **Use literal-block scalars (`|`) for any field containing markdown.** Reserve quoted/folded for single-line strings. Never use folded scalars for code fences.
3. **Imports must label authorship honestly.** If raw_prose is verbatim from upstream, change_summary says "imported verbatim from <path>". If you added rationale/examples/guardrails, change_summary says "scaffold authored by skillsmith around upstream prose preserved in fragment N". Never say "imported" when you authored most of it.
4. **Add an `upstream:` schema field** (optional string, e.g. `mattpocock/skills@<commit>:engineering/zoom-out/SKILL.md`). Populate on import; grep-able.
5. **Worked examples must be either real (cite the file) or labelled "Illustrative".** No invented file paths, domain terms, or APIs presented as canonical.
6. **Each fragment must be retrieval-self-contained.** First sentence names the skill or the action; no dangling pronouns whose referent is in a sibling fragment. Test: read the fragment alone — does the reader know what skill this is from?
7. **Each rationale fragment must contain ≥3 of the obvious query keywords for the skill.** For zoom-out: "architecture", "architectural context", "callers", "module map". Embeddings on short fragments need explicit lexical anchoring.
8. **Maintain a `THIRD_PARTY_LICENSES.md` at repo root.** Every imported source gets a row with origin, license, and the YAML(s) it touched. Required for MIT compliance and provenance.
9. **Pack manifest fragment_count must match `len(yaml.safe_load(file)['fragments'])`.** Add a CI check that hard-fails on drift (you mentioned this exists for install-time; replicate at lint-time).
10. **Fragment minimum and target length.** Aim for 200–800 words; flag fragments under 80 words for review (under-discriminative for qwen3-embedding:0.6b).

---

## 4. Open Questions

1. **raw_prose ↔ fragments policy.** Is raw_prose authoritative or a snapshot? Decide before merging C2 fixes. If authoritative, debugging-strategies and planning need raw_prose extensions now. If snapshot, ship a `prose_authoritative: bool` field and document the retrieval implication (full-text search blind to fragment-only content).
2. **Upstream attribution structure.** Free-text in change_summary or structured `upstream:` field? Recommend structured. Need a one-time pass over existing imports if you add it.
3. **THIRD_PARTY_LICENSES.md scope.** Just mattpocock today, but the corpus already lifts content from agents-plugin, superpowers, and local-workstation. Audit before publishing.
4. **caveman category.** Accept `tooling` or add a `meta`/`interaction` category? Affects category_scope routing.
5. **Re-fragmentation of debugging-strategies 1–15.** Out of scope for this PR but the file is half-broken (C3). Schedule it.
6. **disable-model-invocation analogue.** zoom-out source declares it; skillsmith has no equivalent. Worth modelling? Maps to "user must explicitly invoke; do not auto-route."

---

## Summary

- **2 critical** issues (raw_prose drift in 3 files; one dropped sentence in TDD frag 8).
- **6 important** issues (over-authoring labelled as import x2, fabricated example, voice violation in caveman frag 1, missing license file, weak Stripe claim).
- **7 minor**, **5 nits**.
- Schema validates everywhere; sequences contiguous; manifest counts correct; semver bumps correct.
- The core/engineering pack manifests are clean. The skill files themselves carry the issues.

Recommend fixing C1, C2, I1, I2, I5 before merging. Defer I3/I4/I6 + minors to a follow-up.
