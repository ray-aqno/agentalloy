---
issue: NXS-767
milestone: Agent can request and receive a composed skill (M1)
title: Implement domain fragment retrieval pipeline
type: service
status: todo
generated: 2026-04-22T21:45:00Z
---

# Issue Contract: NXS-767

## Summary
Given a task description + phase + optional domain filters + k, embed the task, retrieve eligible active domain fragments, rank by semantic relevance, prefer structural diversity (setup/execution/verification), and return a bounded candidate set. Pure pipeline; no HTTP.

## Acceptance Criteria
1. Given a task description and phase, when domain retrieval runs, then only fragments from active domain skills that satisfy the runtime filters are eligible.
2. Given eligible fragments, when ranking runs, then the pipeline returns a top-k candidate set ordered by semantic relevance.
3. Given available setup, execution, and verification fragments among the candidates, when the final candidate set is selected, then the pipeline prefers structural diversity rather than returning execution-only fragments.
4. Given no eligible domain fragments, when retrieval runs, then the pipeline returns an explicit empty candidate set without raising a system error.

## Out of Scope
* System-skill retrieval (NXS-771)
* Assembly prompt construction (NXS-768)
* HTTP response mapping (NXS-768)

## Dependencies
* **NXS-766** (active fragment reads)
* **NXS-781** (Ollama client for embeddings)

## Pipeline stages

```python
@dataclass(frozen=True)
class RetrievalResult:
    candidates: list[ActiveFragment]   # ordered; empty list is valid
    eligible_count: int                # pre-ranking count (for telemetry)
    retrieval_ms: int

def retrieve_domain_candidates(
    store: LadybugStore,
    ollama: OllamaClient,
    *,
    task: str,
    phase: str,
    domain_tags: list[str] | None,
    k: int,
) -> RetrievalResult:
    ...
```

**Stage 1 — Eligibility filter:** `get_active_fragments(store, skill_class="domain", categories=phase_to_categories(phase), domain_tags=domain_tags)`. `phase_to_categories` returns the locked list-based mapping below.

**Stage 2 — Embedding:** `ollama.embed(task)` → 768-float query vector.

**Stage 3 — Ranking:** cosine similarity between query vector and each eligible fragment's embedding. If LadybugDB vector index is available (check in NXS-780 notes), use Cypher `CALL QUERY_VECTOR_INDEX(...)`; otherwise in-process numpy cosine.

**Stage 4 — Structural diversity reshuffle:** 
* Take top `2k` by raw similarity (or all eligible if < 2k).
* Within that pool: greedily select k, preferring at each step a fragment whose `fragment_type` is not already in the selected set (priority order: setup, execution, verification, then others). Ties resolved by similarity.
* If pool is all execution-type, return execution-only — the AC says "prefer when available," not "require."

**Stage 5 — Return:** `RetrievalResult` with ordered candidates (reordered so final output reads setup → execution → verification → examples → rationale → guardrail where possible; guardrails are typically system-skill territory but domain fragments may tag one).

## Files to Create
| File | Action |
|------|--------|
| `src/skill_api/retrieval/__init__.py` | create |
| `src/skill_api/retrieval/domain.py` | create (pipeline function + `RetrievalResult` + `phase_to_category` map + ranking + diversity logic) |
| `src/skill_api/retrieval/similarity.py` | create (cosine similarity helper, numpy-based; unit-testable without Ollama) |
| `tests/test_retrieval_eligibility.py` | create (fixtures loaded; domain_tags filter narrows correctly; only domain skills, never system) |
| `tests/test_retrieval_ranking.py` | create (mock Ollama to return known query vector; mock fragment embeddings; assert ordering matches cosine) |
| `tests/test_retrieval_diversity.py` | create (mock candidates with varied fragment_types; assert selected set prefers diverse types) |
| `tests/test_retrieval_empty.py` | create (no eligible fragments → empty result, retrieval_ms still reported, no exception) |
| `tests/test_retrieval_integration.py` | create (`@pytest.mark.integration`: real Ollama, fixture corpus; asserts k=5 returns ≤5 real fragments) |

## Commands
```bash
pytest tests/test_retrieval_eligibility.py tests/test_retrieval_ranking.py tests/test_retrieval_diversity.py tests/test_retrieval_empty.py
pytest -m integration tests/test_retrieval_integration.py
```

## Notes
* **Vector index fallback:** in M0b (NXS-780), if LadybugDB's kuzu version doesn't ship vector index support, this issue runs in-process numpy cosine. Write `similarity.py` to work standalone; the index path is an optimization, not a correctness requirement.
* **`phase_to_categories` mapping (LOCKED v1):**
    * `spec`       → `["spec", "governance", "meta"]`
    * `design`     → `["design", "governance", "meta"]`
    * `qa`         → `["qa", "governance", "meta"]`
    * `build`      → `["build", "ops", "governance", "meta"]`
    * `ops`        → `["ops", "governance", "meta"]`
    * `meta`       → `["meta", "governance"]`
    * `governance` → `["governance", "meta"]`
    
    Rationale: `governance` and `meta` are cross-cutting — retrievable from every phase. `ops` is legitimately useful during `build`. Every other phase maps to its own category plus governance/meta. No phase maps to "any category" (`None`) — whitelisting prevents off-phase leakage.
* **Vector index vs numpy fallback:** if LadybugDB's kuzu version ships HNSW (`CALL QUERY_VECTOR_INDEX(...)`), use it. If not, use `similarity.py` numpy cosine in-process. Log which path is active at service startup (INFO level) so we can verify from logs whether production is on HNSW or numpy. Corpus size (low thousands of fragments) makes numpy performance acceptable; HNSW is a drop-in optimization when available.
* **k bounds:** contract enforces `1 ≤ k ≤ 50`. Retrieval should handle k larger than eligible_count gracefully (return `candidates = eligible` — smaller is fine).
* **Latency measurement:** `retrieval_ms` includes embedding + DB query + ranking + diversity. Use `time.perf_counter_ns()` → ms for consistency with latency contract in NXS-765.
* **Do NOT** raise on empty corpus — return `RetrievalResult(candidates=[], eligible_count=0, retrieval_ms=...)`. NXS-768 handler turns this into `EmptyResult` at the HTTP layer.
* **Do NOT** catch Ollama exceptions here. Let them propagate; NXS-768 maps them to 503 retrieval-stage errors.
