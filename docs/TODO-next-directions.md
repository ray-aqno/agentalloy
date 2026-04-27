# Next directions — captured 2026-04-25

Spoken to-do list captured before they sink into conversation context. None
of these are scoped or scheduled yet — they're starting points for separate
working sessions.

## 1. Skill corpus expansion + cleanup

**Why:** the seeded corpus is small (19 active skills). Several useful
skills sit in `skill-source/` but haven't been triaged or ingested.

**Tasks:**
- [ ] Walk `skill-source/` (all subdirs: `agent-skills/`, `agency-agents/`,
      `agents/`, `local-workstation/`, `vercel-labs-agent-skills/`) and
      build an inventory of every skill candidate.
- [ ] Rank by priority — usefulness for the OSS pitch, coverage gap in the
      current corpus, fit for action vs documentation tasks.
- [ ] Delete everything in `skill-source/` that isn't either a skill file
      or an agent.md / SKILL.md authoring source. Tree shake.
- [ ] Push the high-priority ones through ingest. Re-embed.
- [ ] Re-run a Phase 3 POC slice to confirm the framework's value
      proposition holds (or grows) with the bigger corpus.

## 2. Multi-platform infrastructure variants

**Why:** the current stack is hardcoded to one workstation: Strix Point
NPU + iGPU. The OSS pitch needs to land on the typical local-LLM
machines users actually run.

**Variants needed (priority order):**
- [ ] **Universal CPU+RAM variant.** Run `qwen3.5:0.8b` and
      `embed-gemma:300m` (or equivalent embed model) entirely on CPU+RAM.
      No NPU dependency. This is the *most important* variant — it makes
      the framework runnable on any machine with enough RAM, no
      specialized accelerator required.
- [ ] **Apple Silicon variant.** Use MLX or llama.cpp Metal backend.
      Likely just LM Studio or Ollama swaps with appropriate model
      builds; the skillsmith code itself shouldn't need to change.
- [ ] **NVIDIA variant.** CUDA-backed inference (llama.cpp / vLLM / Ollama
      with GPU). Same shape as Apple variant — different backend, same
      OpenAI-compatible HTTP surface.

**Cross-cutting:**
- [ ] Document required minimums (RAM, VRAM) per variant.
- [ ] Provide config presets (env-var bundles) so users can swap variants
      without editing code.
- [ ] Confirm `OpenAICompatClient` is truly transport-agnostic across
      all four backends.

## 3. Composable Agents (parallel framework)

**Why:** if composable *skills* work (focused fragments retrieved by
similarity, assembled into a task-specific prompt), the same shape might
work for *agents* — focused agent definitions retrieved and composed
per-task instead of giant monolithic agent prompts.

**Open questions to explore:**
- [ ] What's the unit of composition for agents? Skill fragments are
      paragraphs/snippets; agent fragments could be: tool selection,
      operating instructions, escalation rules, output shape, etc.
- [ ] How does retrieval work for agents — same DuckDB cosine search,
      or some kind of graph traversal over agent capabilities?
- [ ] Does the same fragment_type vocabulary (setup / execution /
      verification / guardrail / rationale) apply to agents, or do we
      need a new vocabulary?
- [ ] Same `/compose` API surface, or a sister endpoint?
- [ ] Could the existing storage layer (LadybugDB graph + DuckDB
      vectors) host agents alongside skills with a `node_type`
      discriminator, or would we want a separate store?

## 4. Decision / knowledge base on the same framework

**Why:** the LadybugDB + DuckDB architecture (graph for relationships,
vectors for similarity, fragment-level retrieval) might generalize
beyond skills and code to organizational knowledge bases — ADRs,
decisions, learnings, runbooks, postmortems.

**Open questions to explore:**
- [ ] What's the unit of retrieval for a decision/knowledge base? An
      ADR? A specific decision within an ADR? A consequence/tradeoff?
- [ ] What's the equivalent of "phase" for knowledge retrieval — context
      ("considering option X"), audience ("engineering vs leadership"),
      or just free-text similarity?
- [ ] Do we need authoring + QA gates the way skills do, or is the
      knowledge base mostly hand-curated?
- [ ] Same compose-vs-flat experiment shape: does retrieving 4 ADR
      fragments beat handing the agent the entire ADR archive?
- [ ] Storage decision: same DuckDB file with a `kb_*` schema, or a
      separate `knowledge.duck`?

## 5. Phase 3 POC — replicate on `qwen2.5-coder-14b`

**Why:** POC §15.9 explicitly flags this. The headline numbers
("60-70% fewer tokens, 25% faster, same quality") are currently
only proven against `qwen/qwen3.6-35b-a3b`, which is not the model
most local-LLM users actually run. The OSS pitch's credibility
depends on confirming the pattern transfers to a dense coder model.

**Tasks:**
- [ ] Load `qwen/qwen2.5-coder-14b@q4_k_m` (Q4 quant — what most local
      users will run; current Q8_0 is too heavy for the typical box).
- [ ] Re-run the same 4 variants (k=2, k=4, k=8, no-diversity) on
      both Phase 1 + Phase 2 task sets.
- [ ] Compare totals: do the 70% / 28% / +0.02 quality numbers hold?
- [ ] Document as POC §16. If patterns reproduce, the OSS pitch is
      backed by 2-model evidence and can ship. If not, the pitch
      narrows to "works for MoE models" and we have to think harder.

## 6. Demo recording

**Why:** numbers compel developers; a 60-second video showing
"raw SKILL.md takes 3 min, composed takes 30 sec, same answer"
compels everyone else. Cheap, high-leverage for the pitch.

**Tasks:**
- [ ] Record a side-by-side: same task, same model, two terminals.
      Composed wins visibly within 30 seconds.
- [ ] Add to README and the eventual launch post.

## 7. OSS launch prep

**Why:** the framework is technically ready; the *project* isn't.

**Tasks:**
- [ ] README polish: getting-started in 5 minutes, clear what works /
      what doesn't, links to the §13/14/15/16 findings.
- [ ] Contributing guide.
- [ ] License clarity. The v5.4 brief flagged FastFlowLM's commercial-
      use license needs vendor confirmation; same diligence applies to
      this repo's intended license. Apache 2.0 is the strong default.
- [ ] Public Linear board / GitHub issues with starter tasks tagged
      `good-first-issue` so external contributors can land.
- [ ] Move the seeded skills out of `seeds/` and into a separate repo
      so the corpus can grow on its own cadence.

## 8. Harder eval graders for future POCs

**Why:** §15.9 noted 4 of 5 Phase 2 graders saturate at 1.00 across
all variants. Future eval rounds can't tell us anything about
long-form task quality until the criteria get harder.

**Tasks:**
- [ ] Add LLM-judge tier (was deferred in pre-reg as Tier 2). Run a
      stronger model as a judge on a structured rubric. Costs more but
      catches reward-hacking.
- [ ] Add Tier 3 human spot-check workflow. 20% of runs blind-graded.
- [ ] Tighten the regex criteria where possible (e.g., T10 runbook
      should require non-empty content under each section header,
      not just header presence).

---

## Recommended ordering

Pre-launch:
1. Corpus expansion + cleanup (#1) — direct pitch enabler
2. CPU+RAM variant (#2) + Phase 3 POC (#5) — combined; direct pitch enabler
3. Apple Silicon variant (#2) — major audience
4. Demo recording (#6) + OSS launch prep (#7) — pitch packaging
5. NVIDIA variant (#2) — bonus

Post-launch:
6. Harder graders (#8) — required before the next POC iteration is meaningful
7. Knowledge base (#4) — natural extension
8. Composable agents (#3) — research bet

---

Each of these is its own working session. None are blocking the OSS
pitch — they're directions for after the framework is shipped or in
parallel with shipping prep.
