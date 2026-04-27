"""AC-2, AC-3: fragments of active versions; filters work; inactive fragments excluded."""

from __future__ import annotations

from pathlib import Path

import pytest

from skillsmith.fixtures.loader import load_fixtures
from skillsmith.reads import get_active_fragments, get_active_fragments_for_skill
from skillsmith.storage.ladybug import LadybugStore


@pytest.fixture
def store(tmp_path: Path) -> LadybugStore:
    s = LadybugStore(str(tmp_path / "ladybug"))
    s.open()
    s.migrate()
    load_fixtures(s)
    return s


def test_returns_fragments_with_full_context(store: LadybugStore) -> None:
    fragments = get_active_fragments(store)
    assert fragments, "expected at least one active fragment"
    for f in fragments:
        assert f.fragment_id
        assert f.fragment_type in {
            "guardrail",
            "setup",
            "execution",
            "verification",
            "example",
            "rationale",
        }
        assert f.sequence >= 1
        assert f.content
        assert f.version_id.endswith("-v2")  # only active versions
        assert f.skill_class in {"domain", "system"}


def test_skill_class_filter_domain_only(store: LadybugStore) -> None:
    fragments = get_active_fragments(store, skill_class="domain")
    for f in fragments:
        assert f.skill_class == "domain"


def test_categories_filter_list_based(store: LadybugStore) -> None:
    # Per phase_to_categories locked mapping: design maps to [design, governance, meta]
    fragments = get_active_fragments(store, categories=["design", "governance", "meta"])
    categories = {f.category for f in fragments}
    assert categories <= {"design", "governance", "meta"}
    assert "design" in categories  # fixtures include design-category skills


def test_categories_filter_narrows_correctly(store: LadybugStore) -> None:
    only_build = get_active_fragments(store, skill_class="domain", categories=["build"])
    assert {f.category for f in only_build} == {"build"}


def test_domain_tags_filter(store: LadybugStore) -> None:
    py_frags = get_active_fragments(store, domain_tags=["python"])
    assert py_frags, "expected python-tagged fragments"
    for f in py_frags:
        assert "python" in f.domain_tags


def test_fragments_for_single_skill(store: LadybugStore) -> None:
    frags = get_active_fragments_for_skill(store, "py-fastapi-endpoint-design")
    assert frags
    for f in frags:
        assert f.skill_id == "py-fastapi-endpoint-design"
        assert f.version_id == "py-fastapi-endpoint-design-v2"


def test_unknown_skill_returns_empty(store: LadybugStore) -> None:
    assert get_active_fragments_for_skill(store, "does-not-exist") == []


def test_fragments_ordered_by_sequence(store: LadybugStore) -> None:
    frags = get_active_fragments_for_skill(store, "py-fastapi-endpoint-design")
    assert frags == sorted(frags, key=lambda f: f.sequence)


def test_superseded_version_fragments_excluded(store: LadybugStore) -> None:
    # Manually insert a fragment on a superseded version; confirm it's not returned.
    store.execute(
        """
        CREATE (f:Fragment {
            fragment_id: 'should-not-appear',
            fragment_type: 'execution',
            sequence: 99,
            content: 'from superseded version'
        })
        """
    )
    store.execute(
        """
        MATCH (v:SkillVersion {version_id: 'py-fastapi-endpoint-design-v1'}),
              (f:Fragment {fragment_id: 'should-not-appear'})
        CREATE (v)-[:DECOMPOSES_TO]->(f)
        """
    )
    ids = {f.fragment_id for f in get_active_fragments(store)}
    assert "should-not-appear" not in ids
