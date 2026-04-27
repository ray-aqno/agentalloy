---
issue: NXS-780
milestone: M0 — Scaffolding and infrastructure
title: LadybugDB adapter, SQLite telemetry store, and schema migrations
type: schema-migration
status: todo
generated: 2026-04-22T21:45:00Z
---

# Issue Contract: NXS-780

## Summary
Stand up both storage layers — LadybugDB (graph+vector via `kuzu` Python client) for the runtime knowledge store, and SQLite (via SQLAlchemy) for the `composition_traces` telemetry table. Expose config via env vars and provide `python -m skillsmith.migrate` as the idempotent bootstrap.

## Acceptance Criteria
1. Given empty `LADYBUG_DB_PATH` and `TELEMETRY_DB_PATH`, when `python -m skillsmith.migrate` is run, then both stores are created and the expected node tables, rel tables, and SQL tables exist.
2. Given a migrated LadybugDB, when a test issues a trivial Cypher `MATCH (s:Skill) RETURN count(s)`, then it returns 0 without error.
3. Given a migrated telemetry store, when a test inserts a row into `composition_traces` and queries it back, then all fields round-trip correctly.
4. Given missing environment variables, when config loads, then defaults are applied and logged; when `OLLAMA_BASE_URL` is unset, it defaults to `http://localhost:11434`.
5. Given the migration is run a second time against an existing store, when it completes, then it is idempotent (no errors, no data loss).

## Out of Scope
* Seed data loading (NXS-781)
* Runtime read path (NXS-766)
* Telemetry write path (NXS-773)

## Dependencies
* **NXS-779** (pyproject + FastAPI skeleton)

## Data Model (LadybugDB — from Technical Design §Data model)

**Node tables:**
| Table | Columns |
|-------|---------|
| `Skill` | skill_id (STRING, PK), canonical_name (STRING), category (STRING), skill_class (STRING — 'domain' or 'system'), domain_tags (STRING[]), deprecated (BOOL), always_apply (BOOL), phase_scope (STRING[]), category_scope (STRING[]) |
| `SkillVersion` | version_id (STRING, PK), version_number (INT), authored_at (TIMESTAMP), author (STRING), change_summary (STRING), status (STRING — 'draft'\|'proposed'\|'active'\|'superseded'), raw_prose (STRING) |
| `Fragment` | fragment_id (STRING, PK), fragment_type (STRING), sequence (INT), content (STRING), embedding (FLOAT[768]) |

**Rel tables:**
| Table | From → To |
|-------|-----------|
| `HAS_VERSION` | Skill → SkillVersion |
| `CURRENT_VERSION` | Skill → SkillVersion |
| `DECOMPOSES_TO` | SkillVersion → Fragment |
| `REQUIRES_COMPOSITIONAL` | Skill → Skill |
| `REFERENCES_CONCEPTUAL` | Skill → Skill |

**Vector index:** on `Fragment.embedding` (HNSW) for semantic retrieval in NXS-767.

## Data Model (SQLite — `composition_traces`)
Fields per Technical Design §Telemetry:
* `composition_id` (TEXT, PK, UUID)
* `timestamp` (TIMESTAMP, NOT NULL, default CURRENT_TIMESTAMP)
* `requesting_agent` (TEXT, NULL)
* `phase` (TEXT, NOT NULL)
* `task_prompt` (TEXT, NOT NULL)
* `retrieval_tier` (INTEGER, NULL)
* `assembly_tier` (INTEGER, NULL)
* `domain_fragment_ids` (TEXT — JSON array)
* `system_fragment_ids` (TEXT — JSON array)
* `source_skill_ids` (TEXT — JSON array)
* `output` (TEXT, NULL)
* `result_type` (TEXT — 'composed'|'empty'|'error')
* `latency_retrieval_ms` (INTEGER, NULL)
* `latency_assembly_ms` (INTEGER, NULL)
* `latency_total_ms` (INTEGER, NULL)
* `input_tokens` (INTEGER, NULL)
* `output_tokens` (INTEGER, NULL)
* `error_payload` (TEXT, NULL — JSON)

**Indexes:** `timestamp`, `phase`, `result_type` (covers queryability §Telemetry minimum).

## Files to Create
| File | Action |
|------|--------|
| `src/skill_api/config.py` | create (pydantic-settings `Settings` class; env keys: `OLLAMA_BASE_URL`, `LADYBUG_DB_PATH`, `TELEMETRY_DB_PATH`, `LOG_LEVEL`) |
| `src/skill_api/storage/__init__.py` | create |
| `src/skill_api/storage/ladybug.py` | create (kuzu connection wrapper — `LadybugStore` class with `open()`, `close()`, `__enter__`/`__exit__`, `execute(cypher, params)`, `migrate()`) |
| `src/skill_api/storage/schema_cypher.py` | create (CREATE NODE TABLE + CREATE REL TABLE + CREATE VECTOR INDEX strings) |
| `src/skill_api/storage/telemetry.py` | create (SQLAlchemy declarative `CompositionTrace` model + engine/session factory + `migrate()`) |
| `src/skill_api/migrate.py` | create (CLI `python -m skillsmith.migrate`: calls ladybug.migrate() then telemetry.migrate(), prints summary) |
| `pyproject.toml` | update (add deps: `kuzu`, `sqlalchemy>=2.0`, `pydantic-settings`) |
| `tests/test_storage_ladybug.py` | create (migrate into tmp dir, assert tables exist via `CALL show_tables() RETURN *`, run MATCH count query) |
| `tests/test_storage_telemetry.py` | create (migrate, insert trace, query back, assert fields) |
| `tests/test_config.py` | create (env-var absent → defaults; env-var present → overrides) |
| `tests/test_migrate_idempotent.py` | create (run migrate twice, assert no errors, assert data preserved) |
| `.env.example` | create (document env vars with defaults) |
| `README.md` | update (add env var docs + `python -m skillsmith.migrate` step) |

## Commands
```bash
# Verification
python -m skillsmith.migrate           # fresh stores
python -m skillsmith.migrate           # second run — must be idempotent
pytest tests/test_storage_ladybug.py tests/test_storage_telemetry.py tests/test_config.py tests/test_migrate_idempotent.py
```

## Notes
* **kuzu** is the official Python client for Kuzu/LadybugDB. Install: `uv pip install kuzu`. Embedded DB (like SQLite); single file path.
* **Embedding dimension:** 768 matches `nomic-embed-text`. Hardcode in schema now; if we switch embed models in v1.1, schema migration required.
* **Vector index:** LadybugDB has HNSW index support via `CALL CREATE_VECTOR_INDEX(...)`. Create it in the migration path so NXS-767 doesn't need to. If the kuzu version pinned doesn't support vector indexes yet, fall back to linear scan in NXS-767 (flag in that issue's contract).
* **Idempotent migration:** use `CREATE NODE TABLE IF NOT EXISTS` for Kuzu (supported); SQLAlchemy `create_all()` is inherently idempotent.
* **Config defaults:** `LADYBUG_DB_PATH=./data/ladybug`, `TELEMETRY_DB_PATH=./data/telemetry.db`, `OLLAMA_BASE_URL=http://localhost:11434`. Add `./data/` to `.gitignore`.
* **No connection pooling** on SQLite — single-process service, SQLAlchemy default is fine.
* **Governance fields in Skill:** `always_apply`, `phase_scope`, `category_scope` are defined here (in schema) so NXS-770 can populate them via fixture loader. They're not used by M1 runtime but are load-bearing for M2.
* **Do NOT populate data** in this issue. Migration creates empty schemas only.
