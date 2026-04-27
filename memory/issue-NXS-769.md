---
issue: NXS-769
milestone: Agent can request and receive a composed skill (M1)
title: Implement direct retrieve endpoint
type: controller
status: todo
generated: 2026-04-22T21:45:00Z
---

# Issue Contract: NXS-769

## Summary
A `/retrieve` endpoint that returns active skill content without assembly. Two modes: by-ID (`GET /retrieve/{skill_id}`) and semantic query (`POST /retrieve` with task + phase + k). Emits retrieval-only telemetry traces (no assembly fields). Last issue of M1; completes the M1 demo surface.

## Acceptance Criteria
1. Given a known skill identifier, when the direct retrieve endpoint is called, then it returns the active version raw prose and version metadata without assembly.
2. Given a semantic query and phase, when the direct retrieve endpoint is called, then it returns matching active skill versions and their raw prose without composing a new output.
3. Given a non-active version in the store, when the direct retrieve endpoint is called through normal runtime paths, then it is excluded from default results.
4. Given a successful direct retrieve request, when telemetry is emitted, then it records a retrieval trace shape that does not include assembly-stage fields.

## Out of Scope
* Composed output generation (NXS-768)
* Governance injection (NXS-772)
* Read-skill inspection endpoint (NXS-774)

## Dependencies
* **NXS-766** (active reads)
* **NXS-767** (semantic retrieval pipeline — reused for query mode)
* **NXS-765** (loose — different contract, but conventions carry over)

## Contract

### Request / response shapes

**By-ID (GET):**
```
GET /retrieve/{skill_id}
```
```python
class RetrieveByIdResponse(BaseModel):
    status: Literal["ok"] = "ok"
    skill_id: str
    canonical_name: str
    category: str
    skill_class: Literal["domain", "system"]
    active_version: ActiveVersionMeta
    raw_prose: str

class ActiveVersionMeta(BaseModel):
    version_id: str
    version_number: int
    authored_at: datetime
    author: str
    change_summary: str
```
Returns HTTP 404 if skill not found or has no active version.

**Semantic query (POST):**
```
POST /retrieve
```
```python
class RetrieveQueryRequest(BaseModel):
    task: str = Field(..., min_length=1)
    phase: Literal["spec","design","qa","build","ops","meta","governance"]
    domain_tags: list[str] | None = None
    k: int = Field(default=5, ge=1, le=20)

class RetrieveQueryHit(BaseModel):
    skill_id: str
    version_id: str
    canonical_name: str
    raw_prose: str
    score: float   # cosine similarity

class RetrieveQueryResponse(BaseModel):
    status: Literal["ok"] = "ok"
    results: list[RetrieveQueryHit]
```
Empty `results` returns HTTP 200 (same semantics as compose empty — not an error).

**Error mapping:** Ollama/store failures → HTTP 503 with `stage: retrieval`. Reuse `ErrorResponse` shape from NXS-765.

## Telemetry trace shape (retrieval-only)

Per AC-4: no assembly fields. Reuse `composition_traces` table but populate only retrieval-relevant columns:
* `composition_id` — UUID (prefixed `ret-` for disambiguation in analysis — optional; telemetry still works with plain UUIDs)
* `result_type` — `"retrieve_by_id"` or `"retrieve_query"`
* `phase` — from request (by-id: set to `"meta"` or nullable; query: from request)
* `task_prompt` — the task for query mode; empty string for by-id
* `retrieval_tier` — `null` (no tiering in direct retrieve)
* `assembly_tier` — `null`
* `domain_fragment_ids` / `source_skill_ids` — populated (what was matched)
* `system_fragment_ids` — `null`
* `output` — `null` (no assembly)
* `latency_retrieval_ms` / `latency_total_ms` — measured
* `latency_assembly_ms` — `null`

**Note:** the actual DB write lands in NXS-773 (telemetry persistence). In this issue, compute the trace fields and pass them to a no-op `TelemetryWriter` stub — NXS-773 swaps the stub for a real SQLAlchemy writer. This keeps NXS-773 purely a write-path issue.

## Files to Create/Modify
| File | Action |
|------|--------|
| `src/skill_api/api/retrieve_models.py` | create (all pydantic models above) |
| `src/skill_api/api/retrieve_router.py` | create (GET /retrieve/{skill_id} + POST /retrieve) |
| `src/skill_api/orchestration/retrieve.py` | create (`RetrieveOrchestrator` with `by_id(skill_id)` + `by_query(task, phase, domain_tags, k)`; reuses `retrieve_domain_candidates` then dedupes to skills — returns distinct skill_ids with best-matching fragment score) |
| `src/skill_api/telemetry/__init__.py` | create |
| `src/skill_api/telemetry/writer.py` | create (`TelemetryWriter` protocol + `NullTelemetryWriter` stub; real impl in NXS-773) |
| `src/skill_api/app.py` | modify (mount retrieve router; inject TelemetryWriter stub) |
| `tests/test_retrieve_by_id.py` | create (fixtures loaded → returns raw_prose; 404 on unknown id; superseded version never returned when only that exists) |
| `tests/test_retrieve_query.py` | create (mock embed + fragments → asserts dedup to skills; score ordering) |
| `tests/test_retrieve_empty_query.py` | create (domain_tags that match nothing → 200 with empty results) |
| `tests/test_retrieve_excludes_inactive.py` | create (asserts superseded/draft versions never appear) |
| `tests/test_retrieve_telemetry_shape.py` | create (spy on TelemetryWriter; assert trace fields — no assembly_tier, no assembly_ms) |

## Commands
```bash
pytest tests/test_retrieve_by_id.py tests/test_retrieve_query.py tests/test_retrieve_empty_query.py tests/test_retrieve_excludes_inactive.py tests/test_retrieve_telemetry_shape.py
```

## Notes
* **Dedup semantics in query mode:** retrieval pipeline returns fragments; direct retrieve must return skill-level results. Strategy: rank fragments, then for each unique parent `skill_id` take the best-scoring fragment and use its score as the skill's score. Return top-k *skills* not top-k fragments.
* **`raw_prose` source:** comes from `SkillVersion.raw_prose` (not fragment content). In semantic query mode, the fragment matched produces the score, but the returned `raw_prose` is the whole version's prose.
* **404 vs 200-empty:** by-id with unknown skill → 404 (it's an addressed resource that doesn't exist). Query with empty results → 200 (search semantics). Don't unify.
* **`RetrieveOrchestrator` shares code** with `ComposeOrchestrator` — refactor the shared embedding+retrieval call into a helper if the duplication stings, but don't over-engineer a base class yet.
* **Telemetry stub rationale:** writing a DB stub now means NXS-773 can focus purely on "write this payload to SQLite." Prevents scope creep in either direction.
* **M1 exit criteria:** after this issue merges, `POST /compose` and `GET/POST /retrieve` both work end-to-end against real Ollama + seeded LadybugDB. Everything beyond that (governance, traces persisted, read-skill, health) is M2+.
