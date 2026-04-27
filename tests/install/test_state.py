"""Unit tests for install-state.json handling.

Maps to test-plan.md § Layer 1 — State file handling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from skillsmith.install.state import (
    CURRENT_SCHEMA_VERSION,
    get_step_output,
    is_step_completed,
    load_state,
    record_step,
    save_state,
    state_path,
)


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    """Fake repo root with a pyproject.toml so _repo_root heuristic works."""
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


class TestStateFileCreated:
    """test_state_file_created_on_first_subcommand"""

    def test_fresh_state_has_schema_version(self, repo_root: Path) -> None:
        data = load_state(repo_root)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_save_creates_directory_and_file(self, repo_root: Path) -> None:
        data = load_state(repo_root)
        fp = save_state(data, repo_root)
        assert fp.exists()
        assert fp.name == "install-state.json"
        parsed = json.loads(fp.read_text())
        assert parsed["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_state_path_is_under_user_skillsmith_dir(self, repo_root: Path) -> None:
        # State is now user-scoped (XDG_CONFIG_HOME/skillsmith/), not
        # per-repo. The conftest redirects XDG dirs to tmp_path subdirs.
        fp = state_path(repo_root)
        assert "skillsmith" in str(fp)
        assert fp.name == "install-state.json"
        # Path must NOT live inside the repo any more.
        assert str(fp).find(str(repo_root)) == -1 or "_xdg_config" in str(fp)


class TestStateAppendOnly:
    """test_state_file_append_only_within_run"""

    def test_record_step_appends(self, repo_root: Path) -> None:
        data = load_state(repo_root)
        record_step(data, "detect", extra={"output_digest": "sha256:abc"})
        record_step(data, "recommend-host-targets", extra={"selected": "iGPU"})
        assert len(data["completed_steps"]) == 2
        assert data["completed_steps"][0]["step"] == "detect"
        assert data["completed_steps"][1]["step"] == "recommend-host-targets"

    def test_record_step_preserves_order(self, repo_root: Path) -> None:
        data = load_state(repo_root)
        steps = ["detect", "recommend-host-targets", "recommend-models"]
        for s in steps:
            record_step(data, s)
        assert [e["step"] for e in data["completed_steps"]] == steps


class TestStateSchemaMigration:
    """Schema migration tests across the v0→v1→v2 history."""

    def test_v0_migrated_to_current(self, repo_root: Path) -> None:
        fp = state_path(repo_root)
        fp.parent.mkdir(parents=True, exist_ok=True)
        v0: dict[str, Any] = {
            "schema_version": 0,
            "install_started_at": "2026-01-01T00:00:00Z",
            "completed_steps": [],
        }
        fp.write_text(json.dumps(v0))
        data = load_state(repo_root)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION
        assert "harness_files_written" in data
        # v2 dropped the top-level `harness` and `repo_root` fields.
        assert "harness" not in data
        assert "repo_root" not in data

    def test_v1_migrated_to_v2_drops_top_level_harness(self, repo_root: Path) -> None:
        fp = state_path(repo_root)
        fp.parent.mkdir(parents=True, exist_ok=True)
        v1: dict[str, Any] = {
            "schema_version": 1,
            "completed_steps": [],
            "harness": "claude-code",
            "repo_root": "/some/repo",
            "harness_files_written": [{"path": "/some/repo/CLAUDE.md", "action": "injected_block"}],
        }
        fp.write_text(json.dumps(v1))
        data = load_state(repo_root)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION
        assert "harness" not in data
        assert "repo_root" not in data
        # Existing entries get a `harness` field stamped on them.
        assert data["harness_files_written"][0]["harness"] == "claude-code"


class TestStateNewerThanCode:
    """test_state_file_newer_than_code_errors"""

    def test_future_schema_version_exits_3(self, repo_root: Path) -> None:
        fp = state_path(repo_root)
        fp.parent.mkdir(parents=True, exist_ok=True)
        future = {"schema_version": CURRENT_SCHEMA_VERSION + 1}
        fp.write_text(json.dumps(future))
        with pytest.raises(SystemExit) as exc_info:
            load_state(repo_root)
        assert exc_info.value.code == 3


class TestStateSequentialWrites:
    """test_state_file_consistent_after_concurrent_writes"""

    def test_sequential_saves_produce_valid_json(self, repo_root: Path) -> None:
        data = load_state(repo_root)
        record_step(data, "detect")
        save_state(data, repo_root)
        record_step(data, "recommend-host-targets")
        save_state(data, repo_root)
        # Re-read and verify
        reloaded = load_state(repo_root)
        assert len(reloaded["completed_steps"]) == 2
        assert reloaded["completed_steps"][0]["step"] == "detect"


class TestStateHelpers:
    def test_is_step_completed(self, repo_root: Path) -> None:
        data = load_state(repo_root)
        assert not is_step_completed(data, "detect")
        record_step(data, "detect")
        assert is_step_completed(data, "detect")

    def test_get_step_output(self, repo_root: Path) -> None:
        data = load_state(repo_root)
        assert get_step_output(data, "detect") is None
        record_step(data, "detect", extra={"output_digest": "sha256:test"})
        out = get_step_output(data, "detect")
        assert out is not None
        assert out["output_digest"] == "sha256:test"
