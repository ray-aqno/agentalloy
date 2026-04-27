"""Unit tests for cosine_similarity helper."""

from __future__ import annotations

import math

import pytest

from skillsmith.retrieval.similarity import cosine_similarity


def test_identical_vectors_are_one() -> None:
    v = [1.0, 2.0, 3.0]
    assert math.isclose(cosine_similarity(v, v), 1.0)


def test_orthogonal_vectors_are_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_opposite_vectors_are_minus_one() -> None:
    assert math.isclose(cosine_similarity([1.0, 1.0], [-1.0, -1.0]), -1.0)


def test_zero_vector_returns_zero() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 1.0])
