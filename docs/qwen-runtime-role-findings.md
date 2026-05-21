# Qwen Runtime Role — Findings (2026-05-21)

Captured during signal-detection design discussion. These are verified facts
about the current compose pipeline, recorded so the upcoming signal-detection
spec and any future architectural changes don't accidentally reintroduce
costs that v5.4 already removed.

## Verified: assembly is deterministic Python

Source: `src/skillsmith/orchestration/compose.py`

- `_format_fragments` (lines 213-242) is pure string concatenation: groups
  by skill_id, inserts markdown headers (`# System fragments`,
  `## skill: <id>`, `### <fragment_type> — <fragment_id>`), concatenates
  fragment content. No model call.
- `ASSEMBLY_TIER = 0` is hardcoded (line 45). The field is preserved in
  the response shape for backwards compatibility but always reports 0.
- `AssemblyStageError` (lines 59-62) is vestigial — kept only so old
  callers that `except` it still compile. It is never raised.

## Verified: no generative LLM in the compose path

Module docstring (`compose.py:1-7`):

> Per v5.4: the runtime path holds no generative LLM. `/compose` retrieves
> domain + system fragments and returns the concatenated raw fragment text
> plus provenance. The inference model on the iGPU stitches this into its
> own prompt; no second LLM call happens here.

This is a deliberate architectural commitment, not an oversight or
"not yet implemented" gap. Re-introducing a generative assembly tier
would put back exactly the paid-token cost the v5.4 change removed.

## Qwen's actual model-bound jobs

The compose path uses Qwen for **one** model-bound job and Python for
everything else:

| Job | Mechanism | Model involved |
|---|---|---|
| Embed query | `lm.embed(model, [query])` in `retrieval/domain.py:216` | **Qwen** |
| RRF fusion | `_rrf_fuse` (pure Python) | None |
| Diversity rerank | `diversity_select` (pure Python) | None |
| Assembly | `_format_fragments` (pure Python) | None |
| System retrieval | `filter_applicable_system_skills` (predicate filter) | None |

Outside the compose path, Qwen is also used for:

- **Ingest-time embedding** when re-embedding fragments (`reembed/cli.py`).
- **Planned: phase lock evaluation** — classifier-style yes/no against
  declared gates. Not yet implemented; covered by the upcoming
  signal-detection spec.

That's the entire surface. There is no synthesis, no generation, no
multi-shot reasoning by any LLM (local or remote) inside the runtime
retrieval pipeline.

## Implication for the signal-detection spec

The phase-lock and domain-trigger evaluator should be **non-generative**:
Qwen acts as a classifier (gate met: y/n; domain changed: y/n), not a
synthesizer. Same architectural posture as the compose path.

This shapes the local-compute budget: the signal layer doesn't compete
with any compose-time generation for Qwen's attention — there isn't any.
The cadence math is bounded by retrieval frequency + gate-check
frequency, both of which are small.

## What would invalidate these findings

- Re-introducing an LLM assembly tier (would change `ASSEMBLY_TIER` and
  the docstring, and add a generation call between retrieval and the
  return statement in `compose.py:125`).
- Switching the embedder to a model that requires server-side prompt
  templating before embedding (would add work to the embed call but
  not introduce generation).
- Adding a re-ranker that uses a generative LLM (would land inside
  `retrieval/domain.py` between RRF and diversity_select).

If any future change touches one of those areas, this doc is stale.
