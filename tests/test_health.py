"""Health endpoint tests (NXS-775)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skillsmith.api.health_router import HealthChecker, HealthResponse


# Backward compat: no health_checker in app.state → returns healthy with no dep details.
def test_health_returns_200_healthy_without_lifespan(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


def _mock_checker(
    store_ok: bool = True,
    tel_ok: bool = True,
    embed_ok: bool = True,
    assemble_ok: bool = True,
) -> MagicMock:
    checker = MagicMock(spec=HealthChecker)

    async def _check() -> HealthResponse:
        from skillsmith.api.health_router import DependencyStatus

        def dep(ok: bool, impact: str) -> DependencyStatus:
            return DependencyStatus(
                status="ok" if ok else "unavailable",
                impact=None if ok else impact,
                detail=None if ok else "simulated failure",
            )

        deps = {
            "runtime_store": dep(store_ok, "compose and retrieve requests will fail"),
            "telemetry_store": dep(tel_ok, "trace persistence degraded"),
            "embedding_runtime": dep(embed_ok, "semantic retrieve will fail"),
            "runtime_cache": dep(assemble_ok, "compose requests will fail"),
        }
        if not store_ok:
            overall = "unavailable"
        elif not embed_ok or not assemble_ok or not tel_ok:
            overall = "degraded"
        else:
            overall = "healthy"
        return HealthResponse(status=overall, dependencies=deps)  # type: ignore[arg-type]

    checker.check = _check
    return checker


@pytest.fixture
def client_with_checker(app: FastAPI) -> TestClient:
    app.state.health_checker = _mock_checker()
    with TestClient(app) as c:
        return c


# AC-1: all deps available → healthy
def test_all_deps_available_reports_healthy(app: FastAPI) -> None:
    app.state.health_checker = _mock_checker()
    with TestClient(app) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert all(v["status"] == "ok" for v in body["dependencies"].values())


# AC-2: runtime store unavailable → unavailable with impact
def test_runtime_store_unavailable_reports_unavailable(app: FastAPI) -> None:
    app.state.health_checker = _mock_checker(store_ok=False)
    with TestClient(app) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    dep = body["dependencies"]["runtime_store"]
    assert dep["status"] == "unavailable"
    assert dep["impact"] is not None and "compose" in dep["impact"]


# AC-3: embedding runtime unavailable → degraded
def test_embedding_runtime_unavailable_reports_degraded(app: FastAPI) -> None:
    app.state.health_checker = _mock_checker(embed_ok=False)
    with TestClient(app) as c:
        resp = c.get("/health")
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["embedding_runtime"]["status"] == "unavailable"
    assert body["dependencies"]["embedding_runtime"]["impact"] is not None


# AC-4: telemetry store unavailable → degraded, other deps still ok
def test_telemetry_unavailable_does_not_imply_runtime_failure(app: FastAPI) -> None:
    app.state.health_checker = _mock_checker(tel_ok=False)
    with TestClient(app) as c:
        resp = c.get("/health")
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["telemetry_store"]["status"] == "unavailable"
    assert body["dependencies"]["runtime_store"]["status"] == "ok"
    assert body["dependencies"]["embedding_runtime"]["status"] == "ok"
