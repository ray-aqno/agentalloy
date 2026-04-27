---
issue: NXS-768
milestone: Agent can request and receive a composed skill (M1)
title: Implement composition orchestration and compose handler
type: controller
status: todo
generated: 2026-04-22T21:45:00Z
---

# Issue Contract: NXS-768

## Summary
Replace the 501 stub with a real compose handler. Wire NXS-767's retrieval pipeline to an assembly step (Ollama `generate` against retrieved fragments + task + phase), measure latencies, and map outcomes to the three contract response shapes: `ComposedResult`, `EmptyResult`, or 503 `ErrorResponse`.

## Acceptance Criteria
1. Given a valid compose request with matched domain fragments, when the handler runs, then it returns assembled guidance over HTTP using the defined composed-result contract.
2. Given no matching domain fragments, when the handler runs, then it returns the defined HTTP 200 empty-result shape rather than a 5xx error.
3. Given retrieval-stage failure, when the handler runs, then it returns HTTP 503 with `stage: retrieval` and no partial composition output.
4. Given assembly-stage failure, when the handler runs, then it returns HTTP 503 with `stage: assembly` and no partial composition output.

## Out of Scope
* System-skill inclusion (NXS-771, NXS-772 — but leave seams)
* Telemetry persistence (NXS-773 — but compute all fields)
* Direct retrieve endpoint (NXS-769)

## Dependencies
* **NXS-765** (contract models)
* **NXS-767** (retrieval pipeline)

## Orchestrator design

```python
class ComposeOrchestrator:
    def __init__(self, store: LadybugStore, ollama: OllamaClient): ...

    async def compose(self, req: ComposeRequest) -> ComposedResult | EmptyResult:
        # Step 1: retrieval (wraps retrieve_domain_candidates)
        try:
            retrieval = retrieve_domain_candidates(...)
        except OllamaModelUnavailable as e:
            raise RetrievalStageError("embedding_model_unavailable", str(e)) from e
        except OllamaError as e:
            raise RetrievalStageError("embedding_failed", str(e)) from e
        except Exception as e:
            raise RetrievalStageError("store_unavailable", str(e)) from e

        # Step 2: empty-result fast path
        if not retrieval.candidates:
            return EmptyResult(
                task=req.task, phase=req.phase,
                system_fragments=[],      # NXS-771 will populate
                system_skills_applied=False,
            )

        # Step 3: assembly
        try:
            assembled, assembly_ms, assembly_tier, in_tok, out_tok = await self._assemble(
                task=req.task, phase=req.phase, fragments=retrieval.candidates
            )
        except OllamaModelUnavailable as e:
            raise AssemblyStageError("model_unavailable", str(e),
                available=ErrorAvailable(domain_fragments=[f.fragment_id for f in retrieval.candidates])) from e
        except OllamaError as e:
            raise AssemblyStageError("dependency_unavailable", str(e),
                available=ErrorAvailable(domain_fragments=[f.fragment_id for f in retrieval.candidates])) from e
        except Exception as e:
            raise AssemblyStageError("assembly_failed", str(e)) from e

        # Step 4: map to ComposedResult
        return ComposedResult(
            task=req.task, phase=req.phase,
            output=assembled,
            domain_fragments=[f.fragment_id for f in retrieval.candidates],
            source_skills=list({f.skill_id for f in retrieval.candidates}),
            system_fragments=[],           # NXS-771
            system_skills_applied=False,    # NXS-771
            assembly_tier=assembly_tier,
            latency_ms=LatencyBreakdown(
                retrieval_ms=retrieval.retrieval_ms,
                assembly_ms=assembly_ms,
                total_ms=retrieval.retrieval_ms + assembly_ms,
            ),
        )
```

**Stage-error exceptions → 503 mapping** lives in a FastAPI exception handler in `compose_router.py`:
```python
@app.exception_handler(RetrievalStageError)
async def _(req, exc): return JSONResponse(status_code=503, content=ErrorResponse(stage="retrieval", code=exc.code, message=exc.message, available=exc.available).model_dump())

@app.exception_handler(AssemblyStageError)
async def _(req, exc): return JSONResponse(status_code=503, content=ErrorResponse(stage="assembly", code=exc.code, message=exc.message, available=exc.available).model_dump())
```

## Assembly prompt (v1)

```
You are composing task-specific guidance for an autonomous engineering agent.

# Task
{task}

# Phase
{phase}

# Source fragments
{for each fragment, numbered, with fragment_type + content}

Compose a single, coherent piece of guidance that:
- orders fragments logically (setup → execution → verification → examples → rationale)
- adds minimal connective prose between fragments
- resolves contradictions explicitly or surfaces them
- does not invent information beyond what the fragments provide
- omits any fragment that is irrelevant to the task

Respond with the composed guidance only — no meta-commentary.
```

Assembly tier in v1: always returns `2` (standard). Tier selection is a v1.1 concern — docstring a comment that says so.

Assembly model: `OllamaClient.generate(prompt, model=settings.ASSEMBLY_MODEL)`. `ASSEMBLY_MODEL` config key defaults to `"qwen2.5-coder:14b"` — leave it configurable so the model router can swap in the right tier.

## Files to Create/Modify
| File | Action |
|------|--------|
| `src/skill_api/orchestration/__init__.py` | create |
| `src/skill_api/orchestration/compose.py` | create (`ComposeOrchestrator`, stage error classes) |
| `src/skill_api/orchestration/assembly_prompt.py` | create (prompt template + `build_prompt(task, phase, fragments) -> str`) |
| `src/skill_api/api/compose_router.py` | modify (replace 501 stub: inject orchestrator via Depends; call orchestrator.compose(); register exception handlers) |
| `src/skill_api/config.py` | modify (add `ASSEMBLY_MODEL` key, default `qwen2.5-coder:14b`) |
| `src/skill_api/app.py` | modify (attach state-scoped Orchestrator + dependencies via lifespan) |
| `tests/test_compose_handler_success.py` | create (mock retrieve → candidates; mock ollama.generate → assembled text; assert ComposedResult shape) |
| `tests/test_compose_handler_empty.py` | create (mock retrieve → empty; assert EmptyResult + HTTP 200) |
| `tests/test_compose_handler_retrieval_fail.py` | create (mock retrieve → raises OllamaError; assert HTTP 503 + stage=retrieval) |
| `tests/test_compose_handler_assembly_fail.py` | create (mock generate → OllamaError; assert HTTP 503 + stage=assembly + available.domain_fragments populated) |
| `tests/test_compose_handler_model_unavailable.py` | create (mock generate → OllamaModelUnavailable; assert HTTP 503 + stage=assembly + code=model_unavailable + available.domain_fragments populated). Also: mock embed → OllamaModelUnavailable; assert HTTP 503 + stage=retrieval + code=embedding_model_unavailable. |
| `tests/test_compose_e2e.py` | create (`@pytest.mark.integration`: real Ollama + fixtures → asserts HTTP 200 ComposedResult with ≥1 fragment) |

## Commands
```bash
pytest tests/test_compose_handler_success.py tests/test_compose_handler_empty.py tests/test_compose_handler_retrieval_fail.py tests/test_compose_handler_assembly_fail.py
pytest -m integration tests/test_compose_e2e.py
```

## Notes
* **Async vs sync:** FastAPI handler is `async`. Ollama client can be sync (httpx.Client) — wrap in `asyncio.to_thread()` for blocking calls, or upgrade Ollama client to `httpx.AsyncClient` in NXS-781 and everything is natively async. Prefer the async-client path; it's cheaper.
* **Dependency injection:** use FastAPI `Depends()` + a module-level `get_orchestrator()` provider. Test overrides via `app.dependency_overrides[]`.
* **Lifespan management:** `LadybugStore` and `OllamaClient` should be created once at app startup (FastAPI `lifespan` context), not per-request. Close on shutdown.
* **Empty-result contract gotcha:** `EmptyResult.system_fragments=[]` + `system_skills_applied=False` in v1 because M2 isn't done yet. NXS-771 replaces these values; don't hardcode `False` elsewhere.
* **Token counts:** Ollama's `/api/generate` returns `prompt_eval_count` and `eval_count` for input/output tokens. Wire them through — NXS-773 needs them. Not surfaced on `ComposedResult` (not in contract), but stash on an internal result type for telemetry.
* **Source skill dedup:** `list({f.skill_id for f in ...})` drops ordering. If order matters (first appearance in ranked candidates), use `dict.fromkeys()` trick.
* **Do not** swallow exceptions. Every non-stage exception should produce a 503 with `stage=retrieval` or `stage=assembly` based on where it was raised. Nothing escapes to FastAPI's default 500.
