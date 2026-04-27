---
issue: NXS-765
milestone: Agent can request and receive a composed skill (M1)
title: Define runtime compose API contract
type: config
status: todo
generated: 2026-04-22T21:45:00Z
---

# Issue Contract: NXS-765

## Summary
Define Pydantic models for the compose endpoint's request and response shapes — including composed-success, empty-result, and 503 error responses — so every M1 handler can bind to a single source of truth. No handler logic in this issue; contract definition + OpenAPI wiring only.

## Acceptance Criteria
1. Given a valid task description and phase, when the compose contract is defined, then the request schema includes `task`, `phase`, optional domain filters, optional `k`, and optional `trace_id` or `correlation_id`.
2. Given a successful composition, when the response contract is defined, then it includes composed output, selected fragment identifiers, source skill identifiers, system-skill inclusion metadata, and latency fields.
3. Given no matching domain fragments, when the response contract is defined, then it returns HTTP 200 with an explicit empty-result shape rather than a 5xx error.
4. Given retrieval or assembly failure, when the response contract is defined, then it returns HTTP 503 with stage-specific error information and no partial composition output.

## Out of Scope
* Implementing runtime handlers (NXS-768)
* Defining direct retrieve behavior (NXS-769)
* Telemetry persistence (NXS-773)

## Dependencies
* **NXS-779** (FastAPI app must exist)

## Schema (from Technical Design §API contract design)

### Request — `ComposeRequest`
```python
class ComposeRequest(BaseModel):
    task: str = Field(..., min_length=1, description="Natural language task description")
    phase: Literal["spec", "design", "qa", "build", "ops", "meta", "governance"]
    domain_tags: list[str] | None = None
    k: int = Field(default=10, ge=1, le=50)
    trace_id: str | None = None  # caller-supplied correlation id
```

### Response — `ComposeResponse` (discriminated union via `result_type`)

**Composed (HTTP 200):**
```python
class LatencyBreakdown(BaseModel):
    retrieval_ms: int
    assembly_ms: int
    total_ms: int

class ComposedResult(BaseModel):
    status: Literal["ok"] = "ok"
    result_type: Literal["composed"] = "composed"
    task: str
    phase: str
    output: str
    domain_fragments: list[str]
    source_skills: list[str]
    system_fragments: list[str]
    system_skills_applied: bool
    assembly_tier: int
    latency_ms: LatencyBreakdown
```

**Empty (HTTP 200):**
```python
class EmptyResult(BaseModel):
    status: Literal["ok"] = "ok"
    result_type: Literal["empty"] = "empty"
    task: str
    phase: str
    output: Literal[""] = ""
    domain_fragments: list[str] = []
    source_skills: list[str] = []
    system_fragments: list[str]
    system_skills_applied: bool
    reason: Literal["no_domain_fragments_matched"] = "no_domain_fragments_matched"
```

**Error (HTTP 503):**
```python
class ErrorAvailable(BaseModel):
    domain_fragments: list[str] = []
    system_fragments: list[str] = []

class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    stage: Literal["retrieval", "assembly"]
    code: Literal["dependency_unavailable", "store_unavailable", "assembly_failed", "embedding_failed", "model_unavailable", "embedding_model_unavailable"]
    message: str
    available: ErrorAvailable | None = None
```

### Route signature
```python
@router.post("/compose", response_model=ComposedResult | EmptyResult, responses={503: {"model": ErrorResponse}})
async def compose(req: ComposeRequest) -> ComposedResult | EmptyResult: ...
```

Handler in this issue is a **501 stub** returning `HTTPException(501, "Not implemented — see NXS-768")`. Real implementation lands in NXS-768.

## Files to Create/Modify
| File | Action |
|------|--------|
| `src/skill_api/api/__init__.py` | create |
| `src/skill_api/api/compose_models.py` | create (all pydantic models above) |
| `src/skill_api/api/compose_router.py` | create (APIRouter with POST `/compose` 501-stub handler) |
| `src/skill_api/app.py` | modify (mount compose router under `/` prefix) |
| `tests/test_compose_contract.py` | create (schema validation tests: valid request parses; invalid `phase` rejected; invalid `k` rejected; response models validate expected shapes) |
| `tests/test_compose_openapi.py` | create (assert OpenAPI schema at `/openapi.json` exposes `/compose` with all three response shapes documented) |

## Commands
```bash
pytest tests/test_compose_contract.py tests/test_compose_openapi.py
curl -X POST localhost:8000/compose -H 'Content-Type: application/json' \
  -d '{"task":"build auth","phase":"design"}'
# → expect HTTP 501 (stub) — real handler in NXS-768
```

## Notes
* **Pydantic v2.** Use `Literal[...]` discriminators and `Field(..., description=...)` — OpenAPI docs render off these.
* **No business logic.** This issue is pure schema + stub. Makes downstream issues faster to review.
* **`trace_id` vs `correlation_id`:** spec uses both interchangeably. Canonicalize on `trace_id` in the request; log both `trace_id` and the server-generated `composition_id` in NXS-773.
* **`assembly_tier` values:** design doesn't enumerate them. Use `int` in the contract, document as "1 = fast path, 2 = standard, 3 = heavy" in a comment; NXS-768 locks the concrete values.
* **Response-model union:** FastAPI supports `ComposedResult | EmptyResult` as response_model with discriminator on `result_type`. Confirm OpenAPI output keeps the discriminator. If not, split into two routes is strictly worse; use `responses={}` overrides instead.
* **Error code semantics:**
    * `store_unavailable` — LadybugDB unreachable (retrieval stage)
    * `embedding_failed` — Ollama embedding call failed for reasons other than model absence (retrieval stage)
    * `embedding_model_unavailable` — embedding model (`nomic-embed-text`) not loaded/pulled in Ollama (retrieval stage)
    * `dependency_unavailable` — Ollama unreachable during assembly (assembly stage)
    * `assembly_failed` — Ollama returned a malformed/empty response (assembly stage)
    * `model_unavailable` — assembly model not loaded/pulled in Ollama (assembly stage)
* **CORS:** not required for v1 (solo operator, agents call directly). Don't add middleware.
