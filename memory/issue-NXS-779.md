---
issue: NXS-779
milestone: M0 — Scaffolding and infrastructure
title: Repo scaffolding, tooling, and CI
type: config
status: todo
generated: 2026-04-22T21:45:00Z
---

# Issue Contract: NXS-779

## Summary
Scaffold the Python + FastAPI project (layout, `pyproject.toml`, ruff/pyright/pytest, GitHub Actions CI) and expose a stub `/health` endpoint. First atomic step of M0; unblocks NXS-780 and NXS-765.

## Acceptance Criteria
1. Given a fresh clone, when `ruff check .`, `pyright`, and `pytest` are run in sequence, then all three exit 0.
2. Given the FastAPI app is started locally, when `GET /health` is called, then it returns HTTP 200 with `{"status": "ok"}`.
3. Given a push to the default branch, when CI runs, then lint + typecheck + test jobs all pass.
4. Given the project layout, when a new module is added under `src/skill_api/`, then it is picked up by `pytest` and type-checked by `pyright` without additional config.

## Out of Scope
* Coverage gates
* Release automation
* Docker/Podman builds
* Pre-commit hooks

## Dependencies
* None (first issue of M0)

## Files to Create
| File | Action |
|------|--------|
| `pyproject.toml` | create (project metadata, ruff+pyright+pytest config, deps: fastapi, uvicorn, pydantic, httpx, pytest, ruff, pyright) |
| `src/skill_api/__init__.py` | create (empty) |
| `src/skill_api/app.py` | create (FastAPI app factory + `/health` route) |
| `src/skill_api/__main__.py` | create (uvicorn entrypoint for `python -m skillsmith`) |
| `tests/__init__.py` | create (empty) |
| `tests/test_health.py` | create (FastAPI TestClient asserts 200 + payload) |
| `tests/conftest.py` | create (shared pytest fixtures — app/client) |
| `.github/workflows/ci.yml` | create (ubuntu-latest, Python 3.12, uv setup, run ruff+pyright+pytest) |
| `.gitignore` | create (Python standard + `.venv/`, `*.db`, `.pytest_cache/`) |
| `README.md` | create (run + test commands only) |
| `.python-version` | create (3.12) |

## Commands
```bash
# Setup (run locally first time)
uv venv && uv pip install -e ".[dev]"

# Verification
ruff check .
pyright
pytest

# Run service
python -m skillsmith  # should start uvicorn on :8000
curl localhost:8000/health  # -> {"status": "ok"}
```

## Notes
* **Package manager:** use `uv` (per global CLAUDE.md: pnpm is Node-only; pip/uv for Python). Prefer `uv` over raw pip for speed.
* **Python version:** 3.12 (modern typing without 3.13-only features).
* **Layout:** src-layout (`src/skill_api/`) — idiomatic for packages, prevents implicit imports from the repo root.
* **pyright mode:** `strict` in `pyproject.toml`. Strict from day one is cheaper than retrofitting.
* **ruff config:** enable `E,F,W,I,B,UP,N,SIM` rulesets. No formatter fights — use ruff format as well.
* **CI:** single job, ubuntu-latest. No matrix yet; add one later if multi-version support becomes a requirement.
* **Do NOT add:** Dockerfile, Containerfile, semantic-release, coverage.py gates, pre-commit hooks. Explicitly out of scope.
