"""AC-4: inconsistent CURRENT_VERSION state raises InconsistentActiveVersion."""

from __future__ import annotations

from pathlib import Path

import pytest

from skillsmith.reads import InconsistentActiveVersion, get_active_skills
from skillsmith.storage.ladybug import LadybugStore


@pytest.fixture
def empty_store(tmp_path: Path) -> LadybugStore:
    s = LadybugStore(str(tmp_path / "ladybug"))
    s.open()
    s.migrate()
    return s


def _make_skill(store: LadybugStore, skill_id: str, skill_class: str = "domain") -> None:
    store.execute(
        """
        CREATE (:Skill {
            skill_id: $sid, canonical_name: $sid, category: 'design',
            skill_class: $sc, domain_tags: [], deprecated: false,
            always_apply: false, phase_scope: [], category_scope: []
        })
        """,
        {"sid": skill_id, "sc": skill_class},
    )


def _make_version(store: LadybugStore, skill_id: str, version_id: str, status: str) -> None:
    from datetime import UTC, datetime

    store.execute(
        """
        CREATE (:SkillVersion {
            version_id: $vid, version_number: 1, authored_at: $at,
            author: 'test', change_summary: 't', status: $status, raw_prose: ''
        })
        """,
        {"vid": version_id, "at": datetime.now(UTC), "status": status},
    )
    store.execute(
        """
        MATCH (s:Skill {skill_id: $sid}), (v:SkillVersion {version_id: $vid})
        CREATE (s)-[:HAS_VERSION]->(v)
        """,
        {"sid": skill_id, "vid": version_id},
    )


def _link_current(store: LadybugStore, skill_id: str, version_id: str) -> None:
    store.execute(
        """
        MATCH (s:Skill {skill_id: $sid}), (v:SkillVersion {version_id: $vid})
        CREATE (s)-[:CURRENT_VERSION]->(v)
        """,
        {"sid": skill_id, "vid": version_id},
    )


def test_current_version_points_at_superseded_raises(empty_store: LadybugStore) -> None:
    _make_skill(empty_store, "s1")
    _make_version(empty_store, "s1", "s1-v1", "superseded")
    _link_current(empty_store, "s1", "s1-v1")
    with pytest.raises(InconsistentActiveVersion) as ei:
        get_active_skills(empty_store)
    assert ei.value.skill_id == "s1"
    assert "superseded" in ei.value.reason


def test_active_version_without_current_edge_raises(empty_store: LadybugStore) -> None:
    _make_skill(empty_store, "s2")
    _make_version(empty_store, "s2", "s2-v1", "active")
    # intentionally skip _link_current
    with pytest.raises(InconsistentActiveVersion) as ei:
        get_active_skills(empty_store)
    assert ei.value.skill_id == "s2"
    assert "no CURRENT_VERSION edge" in ei.value.reason


def test_no_active_version_at_all_does_not_raise(empty_store: LadybugStore) -> None:
    # Draft-only skills are legitimately absent from active reads
    _make_skill(empty_store, "s3")
    _make_version(empty_store, "s3", "s3-v1", "draft")
    skills = get_active_skills(empty_store)
    assert skills == []


def test_empty_store_returns_empty(empty_store: LadybugStore) -> None:
    assert get_active_skills(empty_store) == []
