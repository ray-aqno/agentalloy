"""Unit tests for the ``seed-corpus`` subcommand.

Maps to test-plan.md § Seed corpus integrity.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skillsmith.install.subcommands.seed_corpus import (
    SCHEMA_VERSION,
    check_corpus,
)


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


@pytest.fixture()
def no_bundled_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block first-run seed-from-wheel so missing-file tests stay missing.

    Without this, `check_corpus` would auto-copy the real bundled corpus
    out of the wheel into the test's XDG data dir on every call.
    """
    from skillsmith.install import state as install_state

    monkeypatch.setattr(install_state, "bundled_corpus_dir", lambda: None)


@pytest.fixture()
def user_corpus(tmp_path: Path) -> Path:
    """Path to the (test-isolated) user corpus dir created on demand."""
    from skillsmith.install import state as install_state

    p = install_state.corpus_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


class TestMissingFiles:
    def test_missing_duckdb(
        self, repo_root: Path, user_corpus: Path, no_bundled_corpus: None
    ) -> None:
        (user_corpus / "ladybug").mkdir()
        result = check_corpus(repo_root)
        assert result["action"] == "missing_files"
        assert "skills.duck" in str(result.get("missing", []))

    def test_missing_ladybug(
        self, repo_root: Path, user_corpus: Path, no_bundled_corpus: None
    ) -> None:
        (user_corpus / "skills.duck").write_bytes(b"")
        result = check_corpus(repo_root)
        assert result["action"] == "missing_files"
        assert "ladybug" in str(result.get("missing", []))

    def test_missing_both(self, repo_root: Path, no_bundled_corpus: None) -> None:
        result = check_corpus(repo_root)
        assert result["action"] == "missing_files"
        missing = result.get("missing", [])
        assert len(missing) == 2

    def test_remediation_hint(self, repo_root: Path, no_bundled_corpus: None) -> None:
        result = check_corpus(repo_root)
        # Remediation now points at re-installing the package or running
        # install-pack, since the corpus ships in the wheel.
        assert "skillsmith" in result.get("remediation", "")


class TestVerifiedPresent:
    @patch("skillsmith.install.subcommands.seed_corpus._check_duckdb")
    def test_verified_when_above_minimum(
        self, mock_duck: MagicMock, repo_root: Path, user_corpus: Path
    ) -> None:
        (user_corpus / "skills.duck").write_bytes(b"fake")
        (user_corpus / "ladybug").mkdir()
        mock_duck.return_value = {
            "skill_count": 93,
            "fragment_count": 1003,
            "embedding_model": "embed-gemma:300m",
            "embedding_dim": 768,
        }
        result = check_corpus(repo_root)
        assert result["action"] == "verified_present"
        assert result["skill_count"] == 93
        assert result["fragment_count"] == 1003
        assert result["embedding_model"] == "embed-gemma:300m"
        assert result["embedding_dim"] == 768
        assert result["schema_version"] == SCHEMA_VERSION


class TestUnderMinimumSkillCount:
    @patch("skillsmith.install.subcommands.seed_corpus._check_duckdb")
    def test_under_minimum_returns_missing_files(
        self, mock_duck: MagicMock, repo_root: Path, user_corpus: Path
    ) -> None:
        (user_corpus / "skills.duck").write_bytes(b"fake")
        (user_corpus / "ladybug").mkdir()
        mock_duck.return_value = {
            "skill_count": 10,
            "fragment_count": 50,
            "embedding_model": "embed-gemma:300m",
            "embedding_dim": 768,
        }
        result = check_corpus(repo_root)
        assert result["action"] == "missing_files"
        assert result["skill_count"] == 10


class TestNoNetworkCalls:
    @patch("skillsmith.install.subcommands.seed_corpus._check_duckdb")
    def test_no_http_imports(
        self, mock_duck: MagicMock, repo_root: Path, user_corpus: Path
    ) -> None:
        """seed-corpus should make zero network calls."""
        (user_corpus / "skills.duck").write_bytes(b"fake")
        (user_corpus / "ladybug").mkdir()
        mock_duck.return_value = {
            "skill_count": 93,
            "fragment_count": 1003,
            "embedding_model": "embed-gemma:300m",
            "embedding_dim": 768,
        }
        # Patch urllib to detect any network call
        with patch("urllib.request.urlopen", side_effect=AssertionError("Network call detected!")):
            result = check_corpus(repo_root)
        assert result["action"] == "verified_present"


class TestDurationTracking:
    @patch("skillsmith.install.subcommands.seed_corpus._check_duckdb")
    def test_duration_ms_present(
        self, mock_duck: MagicMock, repo_root: Path, user_corpus: Path
    ) -> None:
        (user_corpus / "skills.duck").write_bytes(b"fake")
        (user_corpus / "ladybug").mkdir()
        mock_duck.return_value = {
            "skill_count": 93,
            "fragment_count": 1003,
            "embedding_model": "embed-gemma:300m",
            "embedding_dim": 768,
        }
        result = check_corpus(repo_root)
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
