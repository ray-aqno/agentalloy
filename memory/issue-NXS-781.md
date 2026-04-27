---
issue: NXS-781
milestone: M0 — Scaffolding and infrastructure
title: Ollama client wrapper and dev-test fixture loader
type: service
status: todo
generated: 2026-04-22T21:45:00Z
---

# Issue Contract: NXS-781

## Summary
httpx-based Ollama client wrapper (`embed`, `generate`) plus a dev/test fixture loader that wipes and re-seeds LadybugDB with a small fixed corpus exercising every code path M1–M4 will hit. Fixtures live as YAML under `fixtures/`, loaded by `python -m skillsmith.fixtures load`.

## Acceptance Criteria
1. Given a running Ollama instance with `nomic-embed-text` pulled, when `client.embed("test input")` is called, then it returns a non-empty vector of floats.
2. Given Ollama is unreachable, when `client.embed` or `client.generate` is called, then a typed `OllamaUnavailable` exception is raised with a clear message.
3. Given a migrated-but-empty LadybugDB, when `python -m skillsmith.fixtures load` is run, then the expected counts of skills, versions, and fragments exist and match the fixture data exactly.
4. Given an already-populated LadybugDB, when fixtures load is run again, then it wipes and re-seeds cleanly.
5. Given loaded fixtures, when a test queries for `fragment_type` values, then every one of `{guardrail, setup, execution, verification, example, rationale}` is present.
6. Given loaded fixtures, when a test queries system skills, then at least one exists for each applicability mode: `always_apply=true`, `phase_scope`-only, `category_scope`-only.

## Out of Scope
* Real corpus seeding (user owns separately)
* Retrieval logic (NXS-767)
* Composition (NXS-768)

## Dependencies
* **NXS-780** (LadybugDB adapter + migration must exist)

## Fixture Corpus

**Domain skills (5):**
1. `py-fastapi-endpoint-design` — category: `design`, domain_tags: [`python`, `http`]
2. `py-sqlite-migrations` — category: `build`, domain_tags: [`python`, `sqlite`]
3. `pytest-fixtures-and-mocks` — category: `qa`, domain_tags: [`python`, `testing`]
4. `git-commit-discipline` — category: `ops`, domain_tags: [`git`]
5. `http-error-contract-design` — category: `design`, domain_tags: [`http`, `api`]

**System skills (3):**
1. `sys-governance-always` — `always_apply=true`, phase_scope=null, category_scope=null (fires on every compose)
2. `sys-governance-build-phase` — `always_apply=false`, `phase_scope=["build"]`, category_scope=null
3. `sys-governance-design-category` — `always_apply=false`, phase_scope=null, `category_scope=["design"]`

**Per-skill shape:**
* 2 versions: one `status='active'` (v2), one `status='superseded'` (v1) — exercises active-version filter
* Active version has 4–6 fragments spanning at least 3 distinct `fragment_type` values across the corpus
* **Coverage requirement:** across all fixtures, every fragment_type in `{guardrail, setup, execution, verification, example, rationale}` appears at least once

**Fixture file layout:**
```
fixtures/
├── domain/
│   ├── py-fastapi-endpoint-design.yaml
│   ├── py-sqlite-migrations.yaml
│   ├── pytest-fixtures-and-mocks.yaml
│   ├── git-commit-discipline.yaml
│   └── http-error-contract-design.yaml
└── system/
    ├── sys-governance-always.yaml
    ├── sys-governance-build-phase.yaml
    └── sys-governance-design-category.yaml
```

**YAML schema per file:**
```yaml
skill_id: py-fastapi-endpoint-design
canonical_name: Python FastAPI endpoint design
category: design
skill_class: domain
domain_tags: [python, http]
deprecated: false
always_apply: false
phase_scope: null
category_scope: null
versions:
  - version_id: py-fastapi-endpoint-design-v1
    version_number: 1
    status: superseded
    authored_at: 2026-01-01T00:00:00Z
    author: fixture-seed
    change_summary: initial version
    raw_prose: "..."
    fragments: []  # superseded versions can have empty fragments
  - version_id: py-fastapi-endpoint-design-v2
    version_number: 2
    status: active
    authored_at: 2026-03-01T00:00:00Z
    author: fixture-seed
    change_summary: v2 with fragments
    raw_prose: "..."
    fragments:
      - fragment_id: py-fastapi-endpoint-design-v2-f1
        fragment_type: setup
        sequence: 1
        content: "..."
      - fragment_id: py-fastapi-endpoint-design-v2-f2
        fragment_type: execution
        sequence: 2
        content: "..."
```

## Files to Create
| File | Action |
|------|--------|
| `src/skill_api/ollama/__init__.py` | create |
| `src/skill_api/ollama/client.py` | create (`OllamaClient` with `embed(text)`, `generate(prompt, model=None)`, `OllamaUnavailable` exception; uses `OLLAMA_BASE_URL`; `nomic-embed-text` default for embed) |
| `src/skill_api/fixtures/__init__.py` | create |
| `src/skill_api/fixtures/loader.py` | create (`load()` — wipes Skill/SkillVersion/Fragment + rels, reads YAML, calls OllamaClient.embed for each fragment, inserts via LadybugStore) |
| `src/skill_api/fixtures/__main__.py` | create (CLI: `python -m skillsmith.fixtures load`) |
| `fixtures/domain/*.yaml` | create (5 files, per corpus spec) |
| `fixtures/system/*.yaml` | create (3 files, per corpus spec) |
| `pyproject.toml` | update (add deps: `httpx`, `pyyaml`, `types-pyyaml`) |
| `tests/test_ollama_client.py` | create (monkeypatch `httpx.Client.post` for success, unreachable, timeout, bad-response, and model-not-found 404 + 2xx-error-body shapes; no real Ollama call) |
| `tests/test_fixture_loader.py` | create (requires running Ollama — mark with `@pytest.mark.integration` so CI can skip if no local Ollama; assert counts, fragment_type coverage, applicability coverage) |

## Commands
```bash
# Pre-req: Ollama running on :11434 with nomic-embed-text pulled
ollama pull nomic-embed-text

# Verification
python -m skillsmith.migrate
python -m skillsmith.fixtures load
python -m skillsmith.fixtures load   # second run — must wipe+reseed cleanly
pytest tests/test_ollama_client.py
pytest -m integration tests/test_fixture_loader.py
```

## Notes
* **OllamaClient API:** mirror Ollama's HTTP surface. POST `/api/embeddings` for `embed`; POST `/api/generate` for `generate`. Non-streaming in v1; streaming is a v1.1 concern.
* **Timeouts:** httpx default 5s is too short for `generate` (LLM can take 30s+). Use `httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)`.
* **Exceptions:** all subclass `OllamaError`:
    * `OllamaUnavailable` — connect error, DNS failure, 5xx
    * `OllamaTimeout` — read/connect timeout exceeded
    * `OllamaBadResponse` — malformed JSON / missing expected fields in a 2xx response
    * `OllamaModelUnavailable` — the requested model is not loaded/pulled in Ollama. Detection: Ollama returns HTTP 404 OR a 2xx with body `{"error": "model '...' not found, try pulling it first"}` on `/api/generate` and `/api/embeddings`. Parse both; include `model` name in the exception message. This lets `ComposeOrchestrator` map to `model_unavailable` (assembly) or `embedding_model_unavailable` (retrieval) per the NXS-765 contract.
* **Integration test marker:** `pytest.mark.integration`. CI should run `pytest -m "not integration"` by default; integration tests run locally during dev or in a separate CI job with Ollama service.
* **Fixture realism:** `raw_prose` and `fragment.content` can be short but must be real-ish prose, not lorem ipsum. They will be embedded and ranked in NXS-767 tests — gibberish yields meaningless rankings.
* **Idempotence via wipe:** fixture loader wipes Skill/SkillVersion/Fragment/rels via Cypher `MATCH (n) DETACH DELETE n` before re-inserting. Simpler than diffing.
* **Do NOT** expose fixture loader in the HTTP API. It's a CLI only.
