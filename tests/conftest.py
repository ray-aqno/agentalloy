"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentalloy.app import create_app
from agentalloy.storage.vector_store import VectorStore, open_or_create


@pytest.fixture(autouse=True)
def clear_container_sentinel():
    """Clear AGENTALLOY_DB_LOCK_HELD between every test.

    The sentinel is set in os.environ by stop_service_in_container() and
    cleared by restart_service_in_container(). If a test exercises the stop
    path without the restart path, the sentinel leaks into subsequent tests
    and causes stop_service_in_container() to short-circuit silently.
    """
    os.environ.pop("AGENTALLOY_DB_LOCK_HELD", None)
    yield
    os.environ.pop("AGENTALLOY_DB_LOCK_HELD", None)


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
