"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skillsmith.app import create_app
from skillsmith.storage.vector_store import VectorStore, open_or_create


@pytest.fixture
def app() -> FastAPI:
    # Skip the production lifespan (which opens LadybugDB + Ollama).
    # Per-test fixtures wire dependency_overrides explicitly.
    return create_app(use_default_lifespan=False)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def vector_store(tmp_path: Path) -> Iterator[VectorStore]:
    """Empty DuckDB vector store at a tmp path. Tests that exercise
    compose/retrieve construction use this for the new vector_store
    constructor parameter. Empty store means search_similar returns no
    hits — fine for tests that mock retrieval results anyway."""
    with open_or_create(tmp_path / "test.duck") as vs:
        yield vs
