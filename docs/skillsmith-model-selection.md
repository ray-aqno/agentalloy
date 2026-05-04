# Model Selection Guide — Skill Authoring

**Status:** Working guide for skill authoring model routing
**Last updated:** 2026-04-29

This document describes which Claude model to use for which phase of skill authoring work. Pairs with `skillsmith-architecture-spec.md` (the corpus contract), `skillsmith-pack-inventory.md` (what gets authored), and the authoring reference document the repo agent will produce (the schema, rules, examples, and source discipline requirements).

---

## Recommendation in one line

**Opus 4.7 for pack design and source-grounded drafting; Sonnet 4.6 for refinement and pattern-execution drafting.** The split is not "design vs. drafting" — it's "judgment-required vs. mechanical." Source verification is judgment.

---

## Why model choice matters here

Skill authoring breaks into activities with different cognitive demands. Routing them to the same model wastes effort in one direction or quality in the other. The shape of the work matters more than which phase it nominally belongs to.

### Pack design (Opus)

For each pack, the work is understanding the technology deeply enough to know:

- What the high-leverage skills are
- What the common pitfalls look like
- Which existing resources cover the territory well versus poorly
- Where Claude can add unique value over what's already out there
- Where to draw skill boundaries (one big skill vs. several focused ones)
- Which tags genuinely serve retrieval vs. which are bag-of-tags spray
- Which canonical sources will ground the pack's content

This is judgment-heavy reasoning work. Synthesizing across documentation, identifying non-obvious patterns, deciding what's worth a skill versus what's adequately covered elsewhere. Opus 4.7 is meaningfully better at this than Sonnet.

### Source-grounded drafting (Opus)

When a skill's content depends on facts the agent must verify against canonical sources — language semantics, API behavior, version-specific features, security recommendations — the drafting work includes verification, not just execution. The agent has to:

- Identify the right primary source
- Read it carefully enough to extract accurate claims
- Distinguish documented behavior from common-but-wrong patterns it might pull from training data
- Author claims that match what the source actually says, not what training data suggests
- Fill the verification block with substantive source citations, not boilerplate

This verification is reasoning-shaped, not execution-shaped. Opus is materially better at it. A Sonnet drafting pass that hallucinates a Prisma feature, structures the YAML correctly around the false claim, and passes structural lint is worse than no skill at all — it pollutes the corpus with confident misinformation.

**This is where the original guidance was wrong.** Source-grounded drafting is not "execution against an established design" — it's a second judgment phase running per-skill. Treating it as Sonnet work optimizes for cost and produces unreliable output.

### Pattern-execution drafting (Sonnet)

Some skills don't depend heavily on version-specific or fact-specific source material. Workflow skills (code review checklists, RFC authoring guides, incident response playbooks) are about organizational practice rather than technical fact. Foundation skills on cross-cutting patterns (debugging approaches, error handling philosophy) are stable enough that training-data synthesis is mostly fine.

For these, drafting genuinely is execution. The pattern is established; the work is producing N instances of it within known constraints. Sonnet handles this cleanly and is significantly faster and cheaper.

The test for whether a skill is pattern-execution-shaped: can I draft this confidently from training data without needing to verify specific claims against a source? If yes, Sonnet. If the answer involves any version numbers, API specifics, security guidance, or recently-changed behavior, the answer is no.

### Lint-aware refinement (Sonnet)

When mechanical lint flags a tag as redundant with the title, or when a position marker is missing, the fix is a small local edit. Sonnet is fine. Same for fixing flagged synonym pairs, restating a tag for queryability, or tightening a description.

Semantic lint failures are different — if the agent is told "this claim is off-intent" or "this verification block doesn't actually verify anything," diagnosing why is reasoning work that may need Opus to do well. Diagnose with Opus, redo the local fix with Sonnet.

---

## The routing rule

```
Opus 4.7        → pack design
                → drafting any skill where claims depend on canonical sources
                  (language packs, framework packs, store packs, protocol packs,
                   most domain packs)
                → diagnosing semantic lint failures
                → calibration of first 2–3 packs

Sonnet 4.6      → drafting workflow packs (process content, not technical fact)
                → drafting foundation packs on stable cross-cutting patterns
                → mechanical lint fixes (synonym swaps, missing markers,
                  title-overlap fixes)
                → small local refinements after Opus diagnosis
```

The previous version of this guide oversimplified to "Opus for design, Sonnet for drafting." That undercounts how much drafting is actually reasoning-shaped due to source verification. The honest split is that most domain-tier and most precision-favored tier drafting needs Opus.

---

## Cost calculus (revised)

For the volume contemplated:

```
v1 (NaviStone):         ~29 packs × 5–10 skills/pack = 150–300 skills
General release:        ~185 packs × 5–10 skills/pack = 900–1800 skills
```

Sonnet 4.6 is roughly a fifth the cost of Opus 4.7. The previous version of this guide estimated routing would land at ~30–40% of all-Opus baseline cost. With the revised routing rule (most drafting on Opus due to source verification), the actual cost is closer to:

```
Opus everywhere:        100% (baseline)
Revised routing:        ~70–80% of baseline
```

The savings are smaller than the original estimate, but the quality is dramatically better. Skills that pass structural lint while being factually wrong are net negative — they pollute the corpus and burn cycles in downstream review or correction.

The honest tradeoff: pay closer to Opus rates for content that needs to be right; save Sonnet rates for content where execution is genuinely the work.

---

## Calibration phase

Don't trust the routing rule blindly on day one. Calibrate first.

**Run the first 2–3 packs end-to-end on Opus 4.7.** Use these to:

- Discover what good output looks like at full quality
- Tune the schema if it's not quite authorable as specified
- Establish voice and depth that subsequent drafting can match
- Identify which content types in the corpus genuinely qualify for Sonnet drafting vs. which need Opus
- Validate that source discipline is actually being followed (verification blocks contain real citations, not boilerplate)

After calibration, switch to the routed pattern for the rest. The first few packs are also where you'll find out whether the architecture spec needs adjustments based on what's actually authorable in practice, and that calibration is worth Opus quality.

**Suggested calibration packs:**

1. **`sdd`** (workflow tier) — the v1 forcing function; getting this right validates the workflow class end-to-end. Also tests pattern-execution drafting since workflow content is mostly process.
2. **`postgres`** or **`react`** (precision-favored tier) — tests source-grounded drafting against canonical docs. Good check on whether verification blocks are substantive.
3. **`engineering`** (foundation tier) — tests synthesis-from-training-data drafting where fabrication risk is lower. Good check on whether the agent stays conservative when sources don't anchor the claims.

These three together exercise the full range of authoring shapes: workflow-as-process, technical-fact-with-canonical-source, and synthesized-pattern. After calibration on these, the routing rule should be confident.

---

## When to escalate from Sonnet to Opus mid-work

Triggers for stopping Sonnet drafting and going back to Opus:

- The drafted skill misses the pack's actual job — symptom that pack design was thin
- Multiple drafted skills overlap each other — symptom that skill boundaries weren't sharp in design
- Tags fail quality lint at high rate (>30% of drafted skills) — symptom that retrieval surface wasn't designed deliberately
- Verification or rationale blocks read as filler rather than substance — symptom that the design didn't capture what makes the skill useful
- **Claims in drafted skills don't match what canonical sources actually say** — symptom that the content is more fact-dependent than initially classified, and Sonnet was wrong choice
- **Verification blocks cite sources but the claims don't actually trace to those sources** — symptom of fabrication; the agent is going through motions without grounding

The last two triggers are new and important. If a Sonnet-drafted skill's verification block cites Prisma docs but the claim isn't actually in Prisma docs, that's a fabrication signal. Stop and re-route to Opus for that pack.

---

## Workflow integration

How model selection plugs into actual authoring environments:

### From Claude.ai (chat interface)

Model selection happens per-conversation. Manually switch between Opus for design conversations and either model for drafting conversations depending on the pack type. Keep design and drafting in separate chats so the model context matches the work.

### From Claude Code

Existing SDD pattern likely already configures model-per-skill — design-heavy SDD steps run on Opus, execution-heavy ones on Sonnet. Skill authoring slots into the same pattern, but the routing rule for drafting depends on pack tier rather than being uniform.

### From the API

Route programmatically. Pack-design calls use `claude-opus-4-7`. Drafting calls route based on the pack's expected fact-dependence — packs in `language`, `framework`, `store`, and `protocol` tiers default to Opus; packs in `workflow` tier and stable subsets of `foundation` default to Sonnet. Spend Opus tokens where they protect against fabrication.

---

## When in doubt, default to Opus

Underspending on a hard task and getting unreliable output costs more than the marginal model price. The cost of fabrication isn't visible at draft time — it shows up later when a skill confidently advises a deprecated pattern, a wrong API signature, a security claim that's reversed from current best practice. By the time someone notices, the skill has been retrieved many times.

When uncertain whether a task is reasoning-shaped or execution-shaped, treat it as reasoning-shaped and use Opus. The cost of the wrong call is meaningfully higher in the cheaper-model direction than the more-expensive-model direction.

---

## Summary table

| Activity | Model | Reasoning |
|---|---|---|
| Pack design / skill boundary decisions | Opus 4.7 | Judgment-heavy, compounds downstream |
| Drafting skills with version-specific or API-specific claims | Opus 4.7 | Source verification is reasoning, not execution |
| Drafting skills in `workflow` tier | Sonnet 4.6 | Process content, low fabrication risk |
| Drafting skills in `foundation` tier on stable patterns | Sonnet 4.6 | Synthesis-friendly, low fabrication risk |
| Drafting skills in `language`, `framework`, `store`, `protocol` tiers | Opus 4.7 | High fabrication risk; needs source grounding |
| Drafting skills in `domain` tier | Opus 4.7 (mostly) | Most domain content benefits from grounded authoring |
| Drafting skills in `cross-cutting` tier | Mixed | Pattern depth varies — start with Opus, downshift if drafts are clean |
| Mechanical lint fixes | Sonnet 4.6 | Small local edits |
| Diagnosing semantic lint failures | Opus 4.7 | Reasoning about why a claim is wrong |
| Calibration of first 2–3 packs | Opus 4.7 | Establishes quality bar |
| Unfamiliar domains (fintech, healthcare, etc.) | Opus 4.7 | Less established mental model |
| Workflow packs (skill boundaries non-obvious in design phase) | Opus 4.7 for design, Sonnet for drafting | Design needs reasoning; drafting is execution once design is sharp |
