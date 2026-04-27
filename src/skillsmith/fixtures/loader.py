"""Fixture loader — reads YAML skill files and seeds LadybugDB.

Not a product capability. Only used by tests and by local developers to get a
representative runtime store without going through the real ingest flow.

Per v5.3, embeddings live in DuckDB ``fragment_embeddings``; this loader
only writes the LadybugDB graph (Skill / SkillVersion / Fragment + edges).
After loading fixtures, run ``python -m skillsmith.reembed`` to populate
DuckDB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import yaml

from skillsmith.storage.ladybug import LadybugStore

logger = logging.getLogger(__name__)

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "fixtures"


@dataclass(frozen=True)
class LoadSummary:
    skills: int
    versions: int
    fragments: int


def load_fixtures(
    store: LadybugStore,
    *,
    fixtures_root: Path = FIXTURES_ROOT,
) -> LoadSummary:
    """Wipe Skill/SkillVersion/Fragment nodes and re-seed from YAML fixtures.

    To populate the DuckDB ``fragment_embeddings`` table after loading, run
    ``python -m skillsmith.reembed``.
    """
    _wipe(store)
    skills = _read_fixture_files(fixtures_root)
    logger.info("fixtures_load begin files=%d", len(skills))

    created_skills = 0
    created_versions = 0
    created_fragments = 0

    for skill in skills:
        _insert_skill(store, skill)
        created_skills += 1
        versions: list[dict[str, Any]] = skill["versions"]
        for version in versions:
            _insert_version(store, skill["skill_id"], version)
            created_versions += 1
            if version["status"] == "active":
                _link_current_version(store, skill["skill_id"], version["version_id"])
            fragments: list[dict[str, Any]] = version.get("fragments") or []
            for fragment in fragments:
                _insert_fragment(store, version["version_id"], fragment)
                created_fragments += 1

    summary = LoadSummary(
        skills=created_skills, versions=created_versions, fragments=created_fragments
    )
    logger.info(
        "fixtures_load ok skills=%d versions=%d fragments=%d",
        summary.skills,
        summary.versions,
        summary.fragments,
    )
    return summary


def _wipe(store: LadybugStore) -> None:
    # Kuzu 0.11 doesn't support DETACH DELETE for every edge type in one statement;
    # deleting nodes deletes incident edges automatically in current versions.
    store.execute("MATCH (n) DETACH DELETE n")


def _read_fixture_files(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        raise FileNotFoundError(f"fixtures directory not found: {root}")
    files = sorted([*root.glob("domain/*.yaml"), *root.glob("system/*.yaml")])
    out: list[dict[str, Any]] = []
    for f in files:
        raw: Any = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"invalid fixture (expected mapping): {f}")
        out.append(cast("dict[str, Any]", raw))
    return out


def _insert_skill(store: LadybugStore, skill: dict[str, Any]) -> None:
    store.execute(
        """
        CREATE (:Skill {
            skill_id: $skill_id,
            canonical_name: $canonical_name,
            category: $category,
            skill_class: $skill_class,
            domain_tags: $domain_tags,
            deprecated: $deprecated,
            always_apply: $always_apply,
            phase_scope: $phase_scope,
            category_scope: $category_scope
        })
        """,
        {
            "skill_id": skill["skill_id"],
            "canonical_name": skill["canonical_name"],
            "category": skill["category"],
            "skill_class": skill["skill_class"],
            "domain_tags": skill.get("domain_tags") or [],
            "deprecated": bool(skill.get("deprecated", False)),
            "always_apply": bool(skill.get("always_apply", False)),
            "phase_scope": skill.get("phase_scope") or [],
            "category_scope": skill.get("category_scope") or [],
        },
    )


def _insert_version(store: LadybugStore, skill_id: str, version: dict[str, Any]) -> None:
    authored_at = version.get("authored_at")
    if isinstance(authored_at, str):
        authored_dt = datetime.fromisoformat(authored_at.replace("Z", "+00:00"))
    elif isinstance(authored_at, datetime):
        authored_dt = authored_at
    else:
        raise ValueError(f"invalid authored_at on version {version.get('version_id')}")

    store.execute(
        """
        CREATE (:SkillVersion {
            version_id: $version_id,
            version_number: $version_number,
            authored_at: $authored_at,
            author: $author,
            change_summary: $change_summary,
            status: $status,
            raw_prose: $raw_prose
        })
        """,
        {
            "version_id": version["version_id"],
            "version_number": int(version["version_number"]),
            "authored_at": authored_dt,
            "author": version.get("author", "fixture-seed"),
            "change_summary": version.get("change_summary", ""),
            "status": version["status"],
            "raw_prose": version.get("raw_prose", ""),
        },
    )
    store.execute(
        """
        MATCH (s:Skill {skill_id: $skill_id}), (v:SkillVersion {version_id: $version_id})
        CREATE (s)-[:HAS_VERSION]->(v)
        """,
        {"skill_id": skill_id, "version_id": version["version_id"]},
    )


def _link_current_version(store: LadybugStore, skill_id: str, version_id: str) -> None:
    store.execute(
        """
        MATCH (s:Skill {skill_id: $skill_id}), (v:SkillVersion {version_id: $version_id})
        CREATE (s)-[:CURRENT_VERSION]->(v)
        """,
        {"skill_id": skill_id, "version_id": version_id},
    )


def _insert_fragment(
    store: LadybugStore,
    version_id: str,
    fragment: dict[str, Any],
) -> None:
    store.execute(
        """
        CREATE (:Fragment {
            fragment_id: $fragment_id,
            fragment_type: $fragment_type,
            sequence: $sequence,
            content: $content
        })
        """,
        {
            "fragment_id": fragment["fragment_id"],
            "fragment_type": fragment["fragment_type"],
            "sequence": int(fragment["sequence"]),
            "content": fragment["content"],
        },
    )
    store.execute(
        """
        MATCH (v:SkillVersion {version_id: $version_id}), (f:Fragment {fragment_id: $fragment_id})
        CREATE (v)-[:DECOMPOSES_TO]->(f)
        """,
        {"version_id": version_id, "fragment_id": fragment["fragment_id"]},
    )
