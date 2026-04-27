"""Unit tests for the ``pull-models`` subcommand.

Maps to test-plan.md § Model pulling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from skillsmith.install.subcommands.pull_models import (
    _PRESENCE_CHECKS,  # pyright: ignore[reportPrivateUsage]
    STEP_NAME,
    _auto_pull,  # pyright: ignore[reportPrivateUsage]
    _collect_model_runner_pairs,  # pyright: ignore[reportPrivateUsage]
    _is_model_present_ollama,  # pyright: ignore[reportPrivateUsage]
    pull_models,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


def _recommend_output(
    *,
    embed_model: str = "embeddinggemma",
    embed_runner: str = "ollama",
    ingest_model: str = "qwen3.5:0.8b",
    ingest_runner: str = "ollama",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "host_target": "CPU+RAM",
        "preset": "cpu",
        "options": [
            {
                "default": True,
                "embed_model": embed_model,
                "embed_runner": embed_runner,
                "ingest_model": ingest_model,
                "ingest_runner": ingest_runner,
            },
        ],
    }


# ---------------------------------------------------------------------------
# Pair extraction
# ---------------------------------------------------------------------------


class TestCollectPairs:
    def test_two_distinct_pairs(self) -> None:
        option = {
            "embed_model": "embeddinggemma",
            "embed_runner": "ollama",
            "ingest_model": "qwen3.5:0.8b",
            "ingest_runner": "ollama",
        }
        pairs = _collect_model_runner_pairs(option)
        assert len(pairs) == 2
        assert ("embeddinggemma", "ollama") in pairs
        assert ("qwen3.5:0.8b", "ollama") in pairs

    def test_deduplicates_same_model_runner(self) -> None:
        option = {
            "embed_model": "embeddinggemma",
            "embed_runner": "ollama",
            "ingest_model": "embeddinggemma",
            "ingest_runner": "ollama",
        }
        pairs = _collect_model_runner_pairs(option)
        assert len(pairs) == 1

    def test_mixed_runners(self) -> None:
        option = {
            "embed_model": "embed-gemma:300m",
            "embed_runner": "fastflowlm",
            "ingest_model": "qwen/qwen3.6-35b-a3b",
            "ingest_runner": "lmstudio",
        }
        pairs = _collect_model_runner_pairs(option)
        assert len(pairs) == 2
        assert ("embed-gemma:300m", "fastflowlm") in pairs
        assert ("qwen/qwen3.6-35b-a3b", "lmstudio") in pairs


# ---------------------------------------------------------------------------
# Ollama presence check
# ---------------------------------------------------------------------------


class TestOllamaPresence:
    def test_model_present(self) -> None:
        output = "NAME           ID          SIZE    MODIFIED\nembeddinggemma:latest   abc123   622 MB  2 days ago\n"
        with (
            patch("shutil.which", return_value="/usr/bin/ollama"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=output)
            assert _is_model_present_ollama("embeddinggemma") is True

    def test_model_absent(self) -> None:
        output = "NAME           ID          SIZE    MODIFIED\nother:latest   abc123   100 MB  1 day ago\n"
        with (
            patch("shutil.which", return_value="/usr/bin/ollama"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=output)
            assert _is_model_present_ollama("embeddinggemma") is False

    def test_ollama_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            assert _is_model_present_ollama("embeddinggemma") is False

    def test_tagged_model_match(self) -> None:
        output = "NAME              ID       SIZE    MODIFIED\nqwen3.5:0.8b      xyz789   1.0 GB  1 day ago\n"
        with (
            patch("shutil.which", return_value="/usr/bin/ollama"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=output)
            assert _is_model_present_ollama("qwen3.5:0.8b") is True


# ---------------------------------------------------------------------------
# Auto-pull
# ---------------------------------------------------------------------------


class TestAutoPull:
    def test_successful_pull(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/ollama"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = _auto_pull("ollama", "embeddinggemma")
            assert result["success"] is True
            assert "duration_ms" in result
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["/usr/bin/ollama", "pull", "--", "embeddinggemma"]

    def test_pull_failure(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/ollama"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stderr="connection refused")
            result = _auto_pull("ollama", "embeddinggemma")
            assert result["success"] is False
            assert "connection refused" in result["error"]

    def test_binary_not_found(self) -> None:
        with patch("shutil.which", return_value=None):
            result = _auto_pull("ollama", "embeddinggemma")
            assert result["success"] is False
            assert "not found" in result["error"]

    def test_fastflowlm_pull(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/flm"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = _auto_pull("fastflowlm", "embed-gemma:300m")
            assert result["success"] is True
            args = mock_run.call_args[0][0]
            assert args == ["/usr/bin/flm", "pull", "--", "embed-gemma:300m"]


# ---------------------------------------------------------------------------
# Full pull_models
# ---------------------------------------------------------------------------


class TestPullModels:
    def test_auto_pull_both_models(self, repo_root: Path) -> None:
        models = _recommend_output()

        def always_false(m: str) -> bool:
            return False

        with (
            patch.dict(_PRESENCE_CHECKS, {"ollama": always_false}),
            patch("skillsmith.install.subcommands.pull_models._auto_pull") as mock_pull,
        ):
            mock_pull.return_value = {"success": True, "duration_ms": 100}
            result = pull_models(models, root=repo_root)
        assert result["schema_version"] == 1
        assert len(result["auto_pulled"]) == 2
        assert result["manual_steps_required"] == []
        assert result["skipped_already_present"] == []

    def test_skips_already_present(self, repo_root: Path) -> None:
        models = _recommend_output()

        def always_true(m: str) -> bool:
            return True

        with patch.dict(_PRESENCE_CHECKS, {"ollama": always_true}):
            result = pull_models(models, root=repo_root)
        assert len(result["skipped_already_present"]) == 2
        assert result["auto_pulled"] == []

    def test_manual_steps_for_lmstudio(self, repo_root: Path) -> None:
        models = _recommend_output(
            embed_model="embed-gemma:300m",
            embed_runner="fastflowlm",
            ingest_model="qwen/qwen3.6-35b-a3b",
            ingest_runner="lmstudio",
        )

        def always_false(m: str) -> bool:
            return False

        with (
            patch.dict(_PRESENCE_CHECKS, {"fastflowlm": always_false}),
            patch("skillsmith.install.subcommands.pull_models._auto_pull") as mock_pull,
        ):
            mock_pull.return_value = {"success": True, "duration_ms": 50}
            result = pull_models(models, root=repo_root)
        assert len(result["auto_pulled"]) == 1
        assert result["auto_pulled"][0]["model"] == "embed-gemma:300m"
        assert len(result["manual_steps_required"]) == 1
        assert result["manual_steps_required"][0]["runner"] == "lmstudio"
        assert "qwen/qwen3.6-35b-a3b" in result["manual_steps_required"][0]["instruction"]

    def test_idempotent_skip(self, repo_root: Path) -> None:
        """Second run exits 4 (noop) when step already completed."""
        models = _recommend_output()

        def always_true(m: str) -> bool:
            return True

        with patch.dict(_PRESENCE_CHECKS, {"ollama": always_true}):
            pull_models(models, root=repo_root)
        # Second call should raise SystemExit(4)
        with pytest.raises(SystemExit, match="4"):
            pull_models(models, root=repo_root)

    def test_records_state(self, repo_root: Path) -> None:
        models = _recommend_output()

        def always_true(m: str) -> bool:
            return True

        with patch.dict(_PRESENCE_CHECKS, {"ollama": always_true}):
            pull_models(models, root=repo_root)
        from skillsmith.install.state import is_step_completed, load_state

        st = load_state(repo_root)
        assert is_step_completed(st, STEP_NAME)

    def test_no_options_exits(self, repo_root: Path) -> None:
        with pytest.raises(SystemExit):
            pull_models({"options": []}, root=repo_root)

    def test_pull_error_recorded(self, repo_root: Path) -> None:
        models = _recommend_output()

        def always_false(m: str) -> bool:
            return False

        with (
            patch.dict(_PRESENCE_CHECKS, {"ollama": always_false}),
            patch("skillsmith.install.subcommands.pull_models._auto_pull") as mock_pull,
        ):
            mock_pull.return_value = {
                "success": False,
                "error": "connection refused",
                "duration_ms": 10,
            }
            result = pull_models(models, root=repo_root)
        assert "errors" in result
        assert len(result["errors"]) == 2

    def test_partial_failure_does_not_record_completion(self, repo_root: Path) -> None:
        """If any pull fails, pull-models must NOT mark itself completed —
        otherwise idempotency permanently skips it on rerun."""
        from skillsmith.install.state import is_step_completed, load_state

        models = _recommend_output()

        def always_false(m: str) -> bool:
            return False

        with (
            patch.dict(_PRESENCE_CHECKS, {"ollama": always_false}),
            patch("skillsmith.install.subcommands.pull_models._auto_pull") as mock_pull,
        ):
            mock_pull.return_value = {
                "success": False,
                "error": "connection refused",
                "duration_ms": 10,
            }
            pull_models(models, root=repo_root)
        st = load_state(repo_root)
        assert not is_step_completed(st, "pull-models")
        # And no models_pulled tracking either, since nothing succeeded.
        assert not st.get("models_pulled")

    def test_models_pulled_in_state(self, repo_root: Path) -> None:
        models = _recommend_output()

        def always_false(m: str) -> bool:
            return False

        with (
            patch.dict(_PRESENCE_CHECKS, {"ollama": always_false}),
            patch("skillsmith.install.subcommands.pull_models._auto_pull") as mock_pull,
        ):
            mock_pull.return_value = {"success": True, "duration_ms": 100}
            pull_models(models, root=repo_root)
        from skillsmith.install.state import load_state

        st = load_state(repo_root)
        assert "ollama:embeddinggemma" in st["models_pulled"]
        assert "ollama:qwen3.5:0.8b" in st["models_pulled"]
