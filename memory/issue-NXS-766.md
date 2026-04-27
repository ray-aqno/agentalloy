---
issue: NXS-766
milestone: Agent can request and receive a composed skill (M1)
title: Implement active-version skill and fragment reads
type: service
status: todo
generated: 2026-04-22T21:45:00Z
---

# Issue Contract: NXS-766

## Summary
Implement the read path that resolves active skills → active versions → fragments from LadybugDB. Every downstream runtime read (NXS-767, NXS-769, M2, M3, M4) pulls data through this module. Enforces the non-negotiable rule: only `status='active'` versions are visible by default.

## Acceptance Criteria
1. Given a skill with multiple versions, when runtime reads are executed, then only the active version is returned to compose-time callers.
2. Given an active version with decomposed fragments, when fragment reads are executed, then fragment content, type, sequence, and parent version context are available to downstream retrieval logic.
3. Given draft, proposed, or superseded versions in the store, when runtime reads are executed, then those versions are excluded from default compose-time behavior.
4. Given a missing or inconsistent active-version relationship, when runtime reads are executed, then the read path returns a deterministic error rather than silently selecting a non-active version.

## Out of Scope
* Semantic ranking of domain fragments (NXS-767)
* System-skill applicability evaluation (NXS-771)
* HTTP endpoint handlers (NXS-768, NXS-769)

## Dependencies
* **NXS-780** (LadybugDB schema exists)
* **NXS-781** (fixture data exists for tests)
* **NXS-765** (contract defines caller shape — loose dependency; read layer doesn't import contract types)

## API (module surface)

All functions accept a `LadybugStore` handle (DI for tests).

```python
@dataclass(frozen=True)
class ActiveSkill:
    skill_id: str
    canonical_name: str
    category: str
    skill_class: Literal["domain", "system"]
    domain_tags: list[str]
    always_apply: bool
    phase_scope: list[str] | None
    category_scope: list[str] | None
    active_version_id: str

@dataclass(frozen=True)
class ActiveFragment:
    fragment_id: str
    fragment_type: str
    sequence: int
    content: str
    embedding: list[float]
    skill_id: str           # parent skill
    version_id: str         # parent version
    skill_class: Literal["domain", "system"]
    category: str
    domain_tags: list[str]

class InconsistentActiveVersion(Exception): ...

# Public read functions
def get_active_skills(store, *, skill_class: Literal["domain", "system"] | None = None) -> list[ActiveSkill]: ...
def get_active_skill_by_id(store, skill_id: str) -> ActiveSkill | None: ...
def get_active_fragments(store, *, skill_class: Literal["domain", "system"] | None = None, categories: list[str] | None = None, domain_tags: list[str] | None = None) -> list[ActiveFragment]: ...
def get_active_fragments_for_skill(store, skill_id: str) -> list[ActiveFragment]: ...
```

## Cypher queries (reference)

**Active skills:**
```cypher
MATCH (s:Skill)-[:CURRENT_VERSION]->(v:SkillVersion)
WHERE v.status = 'active' AND s.deprecated = false
RETURN s, v.version_id
```

**Active fragments (with full denormalized context for retrieval):**
```cypher
MATCH (s:Skill)-[:CURRENT_VERSION]->(v:SkillVersion)-[:DECOMPOSES_TO]->(f:Fragment)
WHERE v.status = 'active' AND s.deprecated = false
RETURN f, s.skill_id, v.version_id, s.skill_class, s.category, s.domain_tags
ORDER BY s.skill_id, f.sequence
```

**Consistency guard** (fires `InconsistentActiveVersion`):
* A skill has a `CURRENT_VERSION` edge but the target version has `status != 'active'`
* A skill has no `CURRENT_VERSION` edge but has at least one version with `status = 'active'`
* Return `InconsistentActiveVersion(skill_id=..., reason=...)` — do not silently fall through

## Files to Create
| File | Action |
|------|--------|
| `src/skill_api/reads/__init__.py` | create (re-export public functions + dataclasses + exceptions) |
| `src/skill_api/reads/models.py` | create (`ActiveSkill`, `ActiveFragment` dataclasses) |
| `src/skill_api/reads/active.py` | create (all read functions + consistency guard logic) |
| `tests/test_reads_active_skills.py` | create (fixtures loaded → assert only active versions returned; filter by skill_class returns correct subset) |
| `tests/test_reads_active_fragments.py` | create (fixtures loaded → assert fragments from active versions only; superseded-version fragments NOT returned; category/domain_tags filters work) |
| `tests/test_reads_consistency.py` | create (manually insert inconsistent state via store fixture; assert `InconsistentActiveVersion` raised) |

## Commands
```bash
python -m skillsmith.migrate
python -m skillsmith.fixtures load
pytest tests/test_reads_active_skills.py tests/test_reads_active_fragments.py tests/test_reads_consistency.py
```

## Notes
* **Frozen dataclasses** over Pydantic for the internal domain layer — no validation cost on hot reads, immutable passing between layers.
* **No caching yet.** Reads hit LadybugDB each call. Active corpus is small (tens of skills at most). If profiling later shows a bottleneck, add a TTL cache keyed by skill_class. Don't optimize preemptively.
* **`skill_class` filter:** critical — NXS-767 only wants domain fragments; NXS-771 only wants system fragments. Same read path, different filter arg.
* **`categories` filter is list-based**, not scalar. Cross-cutting categories (`governance`, `meta`, `ops`) are retrievable across multiple phases per the locked `phase_to_category` mapping (see NXS-767). Cypher: `WHERE s.category IN $categories`.
* **Inconsistent active version:** M4 (NXS-778) will surface these via the `/health` endpoint. Raising a deterministic exception here gives that issue something clean to catch.
* **Do not** fetch embeddings in `get_active_skills` — only `get_active_fragments`. Embedding vectors are 768 floats × many fragments; don't pull them unless needed.
* **kuzu returns** rows as tuples / dicts depending on the version. Write a thin row-mapping helper and test it against the installed kuzu version — avoid scattering `row[0]` indexing across the codebase.
