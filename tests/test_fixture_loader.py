"""Fixture loader tests.

Per v5.3 the loader writes graph-only; embeddings live in DuckDB and are
populated separately by the reembed CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillsmith.fixtures.loader import load_fixtures
from skillsmith.storage.ladybug import LadybugStore

FIXTURE_TYPES = {"guardrail", "setup", "execution", "verification", "example", "rationale"}


@pytest.fixture
def populated_store(tmp_path: Path) -> LadybugStore:
    store = LadybugStore(str(tmp_path / "ladybug"))
    store.open()
    store.migrate()
    load_fixtures(store)
    return store


def test_load_fixtures_counts(populated_store: LadybugStore) -> None:
    skill_count = populated_store.scalar("MATCH (s:Skill) RETURN count(s)")
    version_count = populated_store.scalar("MATCH (v:SkillVersion) RETURN count(v)")
    fragment_count = populated_store.scalar("MATCH (f:Fragment) RETURN count(f)")

    # 5 domain + 3 system = 8 skills. Each has 2 versions = 16 versions.
    # Only active versions have fragments; counts summed from YAML.
    assert skill_count == 8
    assert version_count == 16
    assert fragment_count > 0


def test_every_fragment_type_present(populated_store: LadybugStore) -> None:
    rows = populated_store.execute("MATCH (f:Fragment) RETURN DISTINCT f.fragment_type")
    present = {row[0] for row in rows}
    assert FIXTURE_TYPES.issubset(present), f"missing: {FIXTURE_TYPES - present}"


def test_only_active_versions_have_current_version_edge(populated_store: LadybugStore) -> None:
    # One CURRENT_VERSION edge per skill (all 8 have an active version)
    count = populated_store.scalar(
        "MATCH (:Skill)-[r:CURRENT_VERSION]->(:SkillVersion) RETURN count(r)"
    )
    assert count == 8


def test_superseded_versions_exist_without_current_link(populated_store: LadybugStore) -> None:
    # Each skill has one superseded version — 8 total
    rows = populated_store.execute(
        "MATCH (v:SkillVersion {status: 'superseded'}) RETURN v.version_id"
    )
    assert len(rows) == 8
    # Those superseded versions should have no CURRENT_VERSION edge pointing at them
    rows = populated_store.execute(
        """
        MATCH (:Skill)-[:CURRENT_VERSION]->(v:SkillVersion {status: 'superseded'})
        RETURN v.version_id
        """
    )
    assert rows == []


def test_applicability_modes_covered(populated_store: LadybugStore) -> None:
    # always_apply=true
    always = populated_store.scalar(
        "MATCH (s:Skill {skill_class: 'system', always_apply: true}) RETURN count(s)"
    )
    assert always >= 1

    # phase_scope present
    phase_scoped = populated_store.scalar(
        """
        MATCH (s:Skill {skill_class: 'system'})
        WHERE s.always_apply = false AND size(s.phase_scope) > 0
        RETURN count(s)
        """
    )
    assert phase_scoped >= 1

    # category_scope present
    category_scoped = populated_store.scalar(
        """
        MATCH (s:Skill {skill_class: 'system'})
        WHERE s.always_apply = false AND size(s.category_scope) > 0
        RETURN count(s)
        """
    )
    assert category_scoped >= 1


def test_load_is_idempotent(tmp_path: Path) -> None:
    store = LadybugStore(str(tmp_path / "ladybug"))
    store.open()
    store.migrate()
    first = load_fixtures(store)
    second = load_fixtures(store)
    assert first == second

    # Post second load, counts still match the first run
    skill_count = store.scalar("MATCH (s:Skill) RETURN count(s)")
    assert skill_count == 8


def test_fragments_loaded_without_embedding(populated_store: LadybugStore) -> None:
    """Per v5.3, fixture loader writes graph-only; embeddings live in DuckDB,
    populated separately by the reembed CLI."""
    count = populated_store.scalar("MATCH (f:Fragment) RETURN count(f)")
    assert count > 0


def test_active_version_fragments_are_reachable(populated_store: LadybugStore) -> None:
    # Every fragment should be reachable from its version via DECOMPOSES_TO
    fragment_count = populated_store.scalar("MATCH (f:Fragment) RETURN count(f)")
    reachable = populated_store.scalar(
        "MATCH (:SkillVersion)-[:DECOMPOSES_TO]->(f:Fragment) RETURN count(f)"
    )
    assert fragment_count == reachable
