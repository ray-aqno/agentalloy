# Spec: Metadata Prefix in Embedded Fragment Text

**Status:** Proposed
**Owner:** nmeyers
**Date:** 2026-05-21
**Related:** `src/skillsmith/reembed/cli.py`, `src/skillsmith/storage/vector_store.py`, `src/skillsmith/retrieval/domain.py`

## Problem

Today, fragments are embedded as bare `frag.content` (`reembed/cli.py:211`). The `fragment_type`, `category`, and `skill_id` are stored as denormalized DuckDB columns (`vector_store.py:46-58`) but never seen by the embedder. Typed corpora consistently benefit from a small structured prefix in the embedded text — the embedder gets a signal that lets semantically-similar prose with different roles (e.g. a `setup` step vs a `verification` step that both mention "install dependencies") separate in vector space.

The query side already uses Qwen3-Embedding's asymmetric instruct template (`retrieval/domain.py:211-215`). The document side has no equivalent structure. This spec adds one.

## Goal

Prepend a short, deterministic metadata header to fragment text **at embed time only**. The header is not stored in the `prose` column (BM25 must not be polluted with type tags) and is not user-visible.

Success: measurable improvement in retrieval recall@10 on a small golden set with no schema change and no model change.

## Non-goals

- Changing the embedding model or dimension.
- Changing the query template.
- Adding new columns to `fragment_embeddings`.
- Modifying BM25 indexing.

## Design

### Embed-time text shape

In `reembed_fragments` (`reembed/cli.py:209-211`), replace:

```python
vec = _embed_with_retry(embed_fn, frag.content)
```

with:

```python
embed_text = _build_embed_text(frag)
vec = _embed_with_retry(embed_fn, embed_text)
```

Where `_build_embed_text` produces:

```
[type: {fragment_type}] [category: {category}]
{content}
```

Example:

```
[type: execution] [category: testing-pytest]
Run `pytest -xvs tests/` to fail fast on the first error...
```

**Rationale for this shape:**

- Leading bracketed tags are a well-known convention (matches how instruction-tuned models like Qwen3 handle structured hints in plaintext).
- A literal newline separates the header from content so the embedder treats the body as the dominant signal.
- `skill_id` is **excluded** — it's an opaque identifier with no semantic content; including it would inject noise into the embedding.
- `category` is included because categories are human-readable phrases (e.g. `testing-pytest`, `python-packaging`) and carry real signal.

### Query-side symmetry

No change to the query template. Qwen3 is asymmetric by design: queries get `Instruct: ...\nQuery: ...`, documents get bare content (or, with this change, content with a structured header). The instruct template already encodes "retrieve relevant skill instruction fragments" — the document-side tags complement, not duplicate, this.

If recall@10 improves but recall@1 regresses, the fallback is to also prepend a matching task hint to the query (e.g. `[phase: {phase}]`) — but only after measuring.

### Storage

- `prose` column: continues to store **bare `frag.content`** so BM25 ranking is unaffected. (`vector_store.py:58` and `FragmentEmbedding.prose`.)
- `embedding` column: stores the vector derived from the prefixed text.
- `embedding_model` column: bump to `qwen3-embedding:0.6b+meta-v1` to make the embedding generation distinguishable from the bare-content baseline. This lets old and new embeddings coexist during rollout and makes A/B trivial.

### Migration

1. Update `_build_embed_text` in `reembed/cli.py`.
2. Bump `embedding_model` constant or settings field to include the `+meta-v1` suffix.
3. Run reembed with `--force` against a staging DuckDB copy.
4. Run eval (see below) against both DBs.
5. If win, swap in prod; old vectors are deletable in a follow-up.

No schema migration. No dimension change. Fully reversible by re-running reembed with the old text builder.

## Evaluation

The repo currently has no retrieval eval (`tests/retrieval/` are integration tests). Ship a minimal golden set with this change:

- **Location:** `tests/retrieval/golden/queries.jsonl`
- **Size:** 40–60 queries, hand-curated from real `composition_traces` rows where assembly succeeded and the user did not retry.
- **Schema:** `{task, phase, expected_fragment_ids: [...], expected_skill_ids: [...]}`
- **Metric:** recall@10 on `expected_fragment_ids`, plus skill-level recall@5 on `expected_skill_ids` (cheaper to label, more stable signal).
- **Runner:** `python -m skillsmith.retrieval.eval --golden tests/retrieval/golden/queries.jsonl`

### Acceptance criteria

Ship if **all** hold on the golden set:

1. Fragment recall@10 improves by ≥ 3 percentage points (absolute).
2. Skill recall@5 does not regress by more than 1 pp.
3. Median retrieval latency does not regress (this is a string concat — should be free, but measure).

If (1) holds but (2) regresses, investigate before shipping — likely indicates the header is overwhelming short fragments. Mitigation: drop `category` from the header for fragments under N tokens.

## Risks

| Risk | Mitigation |
|---|---|
| Qwen3 was not trained on `[type: x]`-style prefixes; embedding distribution may shift unpredictably | The `embedding_model` suffix lets us A/B; the golden set catches regressions before prod swap. |
| Short fragments (e.g. 1-line verification steps) become dominated by the header | If observed, gate header on `len(content) > 80 chars` or drop `category` for short content. Decide from eval data, not upfront. |
| Tags duplicate signal already in content (a `setup` fragment often starts with "Install...") | Real if measured; if recall doesn't improve, this is why. Roll back is free. |
| `category` values drift over time and break old embeddings | Already true for the current scheme — `category` filtering is in the hot path (`vector_store.search_similar`). No new risk. |

## Out of scope (followups)

- **Phase-aware query prefixes.** If results suggest the embedder benefits from document tags, the next experiment is `[phase: build] Instruct: ... Query: ...` on the query side. Spec separately.
- **Tuning the guessed phase RRF weights** (`domain.py:34-46`). Independent change; needs the same golden set.
- **Diversity rerank cost gate.** Independent.

## Open questions

1. Should `fragment_type` use the raw enum value or a humanized form (`execution` vs `Execution step`)? Default to raw; the embedder tokenizes both fine and raw is stable.
2. Do we want a `--text-builder=bare|meta-v1` flag on `reembed` for clean A/B, or rely on `embedding_model` suffix only? Recommend the flag — it's 5 lines and makes the eval script trivial.
