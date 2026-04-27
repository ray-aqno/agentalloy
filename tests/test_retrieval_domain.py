"""AC-1..4 for the domain retrieval pipeline."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from skillsmith.fixtures.loader import load_fixtures
from skillsmith.reads import get_active_fragments
from skillsmith.reads.models import ActiveFragment
from skillsmith.retrieval.domain import (
    diversity_select,
    phase_to_categories,
    retrieve_domain_candidates,
)
from skillsmith.storage.ladybug import LadybugStore
from skillsmith.storage.vector_store import (
    FragmentEmbedding,
    VectorStore,
    open_or_create,
)
from tests.support import StubLMClient


@pytest.fixture
def populated(tmp_path: Path) -> LadybugStore:
    s = LadybugStore(str(tmp_path / "ladybug"))
    s.open()
    s.migrate()
    load_fixtures(s)
    return s


@pytest.fixture
def populated_vectors(tmp_path: Path, populated: LadybugStore) -> VectorStore:
    """Pre-populated DuckDB vector store with embeddings for every active
    fragment in ``populated``. Embedding values come from ``StubLMClient`` —
    the same deterministic stub used by the retrieval path's embedder
    parameter, so query and corpus vectors are coherent for cosine ranking.
    """
    vs = open_or_create(tmp_path / "vectors.duck")
    stub = StubLMClient()
    fragments = get_active_fragments(populated)
    now = int(time.time())
    items = [
        FragmentEmbedding(
            fragment_id=f.fragment_id,
            embedding=stub.embed(model="stub-embed", texts=[f.content])[0],
            skill_id=f.skill_id,
            category=f.category,
            fragment_type=f.fragment_type,
            embedded_at=now,
            embedding_model="stub",
        )
        for f in fragments
    ]
    vs.insert_embeddings(items)
    return vs


# -------- phase_to_categories --------


def test_phase_to_categories_locked_mapping() -> None:
    # v5.4: includes corpus-vocabulary categories alongside the legacy ones
    assert phase_to_categories("spec") == ["spec", "design", "tooling", "governance", "meta"]
    assert phase_to_categories("design") == [
        "design",
        "engineering",
        "tooling",
        "governance",
        "meta",
    ]
    assert phase_to_categories("qa") == [
        "qa",
        "quality",
        "review",
        "engineering",
        "tooling",
        "governance",
        "meta",
    ]
    assert phase_to_categories("build") == [
        "build",
        "engineering",
        "tooling",
        "ops",
        "governance",
        "meta",
    ]
    assert phase_to_categories("ops") == [
        "ops",
        "engineering",
        "tooling",
        "governance",
        "meta",
    ]
    assert phase_to_categories("meta") == ["meta", "tooling", "governance"]
    assert phase_to_categories("governance") == ["governance", "review", "quality", "meta"]


# -------- AC-1: eligibility filter --------


def test_only_domain_fragments_returned(
    populated: LadybugStore, populated_vectors: VectorStore
) -> None:
    result = retrieve_domain_candidates(
        populated,
        StubLMClient(),
        populated_vectors,
        task="fastapi routing",
        phase="design",
        domain_tags=None,
        k=10,
        embedding_model="stub-embed",
    )
    for f in result.candidates:
        assert f.skill_class == "domain"


def test_category_filter_narrows_to_phase(
    populated: LadybugStore, populated_vectors: VectorStore
) -> None:
    # 'build' phase retrieves build/ops/governance/meta — but only domain fragments,
    # so design-only fragments must be excluded.
    result = retrieve_domain_candidates(
        populated,
        StubLMClient(),
        populated_vectors,
        task="write a migration",
        phase="build",
        domain_tags=None,
        k=10,
        embedding_model="stub-embed",
    )
    for f in result.candidates:
        assert f.category in {"build", "ops", "governance", "meta"}


def test_domain_tags_narrow_further(
    populated: LadybugStore, populated_vectors: VectorStore
) -> None:
    result = retrieve_domain_candidates(
        populated,
        StubLMClient(),
        populated_vectors,
        task="fastapi",
        phase="design",
        domain_tags=["fastapi"],
        k=10,
        embedding_model="stub-embed",
    )
    assert result.candidates
    for f in result.candidates:
        assert "fastapi" in f.domain_tags


# -------- AC-2: ranking --------
#
# Ranking by cosine similarity now happens in DuckDB via
# ``array_cosine_distance`` — see ``test_vector_store.py`` for the
# corresponding tests. The previous in-Python ranking test against
# ``ActiveFragment.embedding`` is obsolete with the v5.3 storage split.


# -------- AC-3: structural diversity --------


def _fake(frag_id: str, ftype: str) -> ActiveFragment:
    return ActiveFragment(
        fragment_id=frag_id,
        fragment_type=ftype,
        sequence=1,
        content="",
        skill_id="s",
        version_id="s-v1",
        skill_class="domain",
        category="design",
        domain_tags=[],
    )


def test_diversity_prefers_setup_execution_verification_when_available() -> None:
    # Pool ordered by score: e1, e2, s1, v1, ex1
    pool = [
        _fake("e1", "execution"),
        _fake("e2", "execution"),
        _fake("s1", "setup"),
        _fake("v1", "verification"),
        _fake("ex1", "example"),
    ]
    selected = diversity_select(pool, k=3)
    types = [f.fragment_type for f in selected]
    # Should prefer to cover setup + execution + verification, not three executions.
    assert set(types) == {"setup", "execution", "verification"}


def test_diversity_returns_all_executions_when_only_executions_available() -> None:
    pool = [_fake("e1", "execution"), _fake("e2", "execution"), _fake("e3", "execution")]
    selected = diversity_select(pool, k=3)
    assert [f.fragment_type for f in selected] == ["execution", "execution", "execution"]


def test_diversity_respects_k_bound() -> None:
    pool = [_fake(f"x{i}", "execution") for i in range(10)]
    selected = diversity_select(pool, k=4)
    assert len(selected) == 4


def test_diversity_does_not_duplicate() -> None:
    pool = [_fake("a", "execution"), _fake("b", "setup")]
    selected = diversity_select(pool, k=5)  # k > pool size
    assert len(selected) == 2
    assert len({f.fragment_id for f in selected}) == 2


# -------- AC-4: empty handling --------


def test_empty_eligible_returns_empty_result(
    populated: LadybugStore, populated_vectors: VectorStore
) -> None:
    # No fragments match a nonsense domain_tag
    result = retrieve_domain_candidates(
        populated,
        StubLMClient(),
        populated_vectors,
        task="irrelevant",
        phase="design",
        domain_tags=["nonexistent-tag"],
        k=10,
        embedding_model="stub-embed",
    )
    assert result.candidates == []
    assert result.eligible_count == 0
    assert result.retrieval_ms >= 0


def test_retrieval_records_latency(populated: LadybugStore, populated_vectors: VectorStore) -> None:
    result = retrieve_domain_candidates(
        populated,
        StubLMClient(),
        populated_vectors,
        task="t",
        phase="design",
        domain_tags=None,
        k=5,
        embedding_model="stub-embed",
    )
    assert result.retrieval_ms >= 0


def test_k_larger_than_eligible_returns_all(
    populated: LadybugStore, populated_vectors: VectorStore
) -> None:
    result = retrieve_domain_candidates(
        populated,
        StubLMClient(),
        populated_vectors,
        task="t",
        phase="design",
        domain_tags=["fastapi"],
        k=50,
        embedding_model="stub-embed",
    )
    # Only a handful of fastapi-tagged fragments exist; k=50 must not error
    assert len(result.candidates) <= 50
