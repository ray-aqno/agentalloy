"""Tests for reembed CLI and vector_store FTS rebuild retry."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skillsmith.reembed.cli import (
    EXIT_OK,
)
from skillsmith.reembed.cli import (
    main as reembed_main,
)
from skillsmith.storage.vector_store import VectorStore

# ---------------------------------------------------------------------------
# --rebuild-fts flag
# ---------------------------------------------------------------------------


def test_rebuild_fts_flag_accepted() -> None:
    """--rebuild-fts is accepted as valid CLI (dry-run mode)."""
    with (
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli._is_service_running", return_value=False),
    ):
        mock_settings.return_value.ladybug_db_path = "/tmp/test/ladybug.db"
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 0
        mock_vs.fragment_ids_present.return_value = set()

        # dry-run should exit OK with --rebuild-fts
        code = reembed_main(["--rebuild-fts", "--dry-run"])
        assert code == EXIT_OK


def test_rebuild_fts_runs_when_zero_fragments(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """--rebuild-fts triggers rebuild_fts_index when fragments is empty."""
    # Mock the LadybugStore and vector_store so we can control discovery
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=False),
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        # Mock LadybugStore context manager
        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []  # no fragments

        # Mock VectorStore context manager
        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()

        with caplog.at_level(logging.INFO):
            code = reembed_main(["--rebuild-fts"])

        assert code == EXIT_OK
        mock_vs.rebuild_fts_index.assert_called_once()
        assert "running --rebuild-fts only" in caplog.text or "rebuild-fts requested" in caplog.text


def test_no_rebuild_without_flag_when_zero_fragments(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Without --rebuild-fts, rebuild_fts_index is NOT called when fragments is empty."""
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=False),
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []  # no fragments

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()

        with caplog.at_level(logging.INFO):
            code = reembed_main([])

        assert code == EXIT_OK
        mock_vs.rebuild_fts_index.assert_not_called()
        assert "nothing to do" in caplog.text


def test_rebuild_fts_exit_ok_on_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """When rebuild_fts_index raises, exit code is still EXIT_OK."""
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=False),
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()
        mock_vs.rebuild_fts_index.side_effect = Exception("stopwords has been deleted")

        with caplog.at_level(logging.WARNING):
            code = reembed_main(["--rebuild-fts"])

        assert code == EXIT_OK
        assert "BM25 leg degraded" in caplog.text


# ---------------------------------------------------------------------------
# VectorStore.rebuild_fts_index retry
# ---------------------------------------------------------------------------


def test_rebuild_fts_retry_on_stopwords_error(tmp_path: Path) -> None:
    """rebuild_fts_index retries up to 3 times on the stopwords catalog race."""
    conn = MagicMock()
    create_count = 0

    def mock_execute(sql: str, *a: object, **kw: object) -> None:
        nonlocal create_count
        if "create_fts_index" in sql:
            create_count += 1
            if create_count < 3:
                raise Exception("subject 'stopwords' has been deleted")
        # CHECKPOINT, drop_fts_index: all succeed
        return None

    conn.execute = mock_execute
    vs = VectorStore(conn)  # type: ignore[arg-type]

    # Patch time.sleep so the retry path doesn't actually sleep
    with patch("time.sleep"):
        # Should not raise - third retry succeeds
        vs.rebuild_fts_index()

    # Verify create_fts_index was attempted 3 times
    assert create_count == 3


def test_rebuild_fts_no_retry_on_non_transient_error(tmp_path: Path) -> None:
    """rebuild_fts_index does NOT retry non-transient errors."""
    conn = MagicMock()
    create_count = 0

    def mock_execute(sql: str, *a: object, **kw: object) -> None:
        nonlocal create_count
        if "create_fts_index" in sql:
            create_count += 1
            raise Exception('Extension "fts" not loaded')
        return None

    conn.execute = mock_execute
    vs = VectorStore(conn)  # type: ignore[arg-type]

    with pytest.raises(Exception, match='Extension "fts" not loaded'):
        vs.rebuild_fts_index()

    # Only ONE create_fts_index call (no retry)
    assert create_count == 1


# ---------------------------------------------------------------------------
# Service management
# ---------------------------------------------------------------------------


def test_detect_service_manager_linux() -> None:
    """_detect_service_manager returns 'systemd' on Linux with systemctl."""
    from skillsmith.reembed.cli import (
        _detect_service_manager,  # pyright: ignore[reportPrivateUsage]
    )

    with (
        patch("platform.system", return_value="Linux"),
        patch("shutil.which", return_value="/usr/bin/systemctl"),
    ):
        assert _detect_service_manager() == "systemd"


def test_detect_service_manager_macos() -> None:
    """_detect_service_manager returns 'launchd' on macOS with launchctl."""
    from skillsmith.reembed.cli import (
        _detect_service_manager,  # pyright: ignore[reportPrivateUsage]
    )

    with (
        patch("platform.system", return_value="Darwin"),
        patch("shutil.which", return_value="/bin/launchctl"),
    ):
        assert _detect_service_manager() == "launchd"


def test_detect_service_manager_none() -> None:
    """_detect_service_manager returns None when no service manager found."""
    from skillsmith.reembed.cli import (
        _detect_service_manager,  # pyright: ignore[reportPrivateUsage]
    )

    with (
        patch("platform.system", return_value="Linux"),
        patch("shutil.which", return_value=None),
    ):
        assert _detect_service_manager() is None


def test_is_service_running_systemd() -> None:
    """_is_service_running returns True when systemd reports active."""
    from skillsmith.reembed.cli import _is_service_running  # pyright: ignore[reportPrivateUsage]

    mock_result = MagicMock()
    mock_result.stdout = "active\n"
    mock_result.returncode = 0

    with (
        patch("platform.system", return_value="Linux"),
        patch("shutil.which", return_value="/usr/bin/systemctl"),
        patch("subprocess.run", return_value=mock_result),
    ):
        assert _is_service_running() is True


def test_is_service_running_systemd_inactive() -> None:
    """_is_service_running returns False when systemd reports inactive."""
    from skillsmith.reembed.cli import _is_service_running  # pyright: ignore[reportPrivateUsage]

    mock_result = MagicMock()
    mock_result.stdout = "inactive\n"
    mock_result.returncode = 3

    with (
        patch("platform.system", return_value="Linux"),
        patch("shutil.which", return_value="/usr/bin/systemctl"),
        patch("subprocess.run", return_value=mock_result),
    ):
        assert _is_service_running() is False


def test_is_service_running_no_service_manager() -> None:
    """_is_service_running returns False when no service manager found."""
    from skillsmith.reembed.cli import _is_service_running  # pyright: ignore[reportPrivateUsage]

    with (
        patch("platform.system", return_value="Linux"),
        patch("shutil.which", return_value=None),
    ):
        assert _is_service_running() is False


def test_stop_service_systemd() -> None:
    """_stop_service stops the systemd service."""
    from skillsmith.reembed.cli import _stop_service  # pyright: ignore[reportPrivateUsage]

    with (
        patch("platform.system", return_value="Linux"),
        patch("shutil.which", return_value="/usr/bin/systemctl"),
        patch("subprocess.run") as mock_run,
    ):
        result = _stop_service()
        assert result is True
        mock_run.assert_called_once()
        assert "systemctl" in mock_run.call_args[0][0]
        assert "--user" in mock_run.call_args[0][0]
        assert "stop" in mock_run.call_args[0][0]


def test_stop_service_systemd_failure() -> None:
    """_stop_service returns False when systemd stop fails."""
    from skillsmith.reembed.cli import _stop_service  # pyright: ignore[reportPrivateUsage]

    with (
        patch("platform.system", return_value="Linux"),
        patch("shutil.which", return_value="/usr/bin/systemctl"),
        patch("subprocess.run", side_effect=OSError("no DBUS")),
    ):
        result = _stop_service()
        assert result is False


def test_restart_service_systemd() -> None:
    """_restart_service starts the systemd service."""
    from skillsmith.reembed.cli import _restart_service  # pyright: ignore[reportPrivateUsage]

    with (
        patch("platform.system", return_value="Linux"),
        patch("shutil.which", return_value="/usr/bin/systemctl"),
        patch("subprocess.run") as mock_run,
    ):
        _restart_service()
        mock_run.assert_called_once()
        assert "systemctl" in mock_run.call_args[0][0]
        assert "--user" in mock_run.call_args[0][0]
        assert "start" in mock_run.call_args[0][0]


# ---------------------------------------------------------------------------
# Pre-flight service stop/restart integration
# ---------------------------------------------------------------------------


def test_reembed_stops_and_restarts_service(tmp_path: Path) -> None:
    """reembed stops service before DB access and restarts after (unless --no-restart)."""
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=True),
        patch("skillsmith.reembed.cli._stop_service", return_value=True) as mock_stop,
        patch("skillsmith.reembed.cli._restart_service") as mock_restart,
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()

        code = reembed_main(["--rebuild-fts"])

        assert code == EXIT_OK
        mock_stop.assert_called_once()
        mock_restart.assert_called_once()


def test_reembed_no_restart_flag(tmp_path: Path) -> None:
    """--no-restart prevents automatic service restart."""
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=True),
        patch("skillsmith.reembed.cli._stop_service", return_value=True),
        patch("skillsmith.reembed.cli._restart_service") as mock_restart,
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()

        code = reembed_main(["--rebuild-fts", "--no-restart"])

        assert code == EXIT_OK
        mock_restart.assert_not_called()


def test_reembed_no_service_skip_stop(tmp_path: Path) -> None:
    """When service is not running, skip stop and restart steps."""
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=False),
        patch("skillsmith.reembed.cli._stop_service") as mock_stop,
        patch("skillsmith.reembed.cli._restart_service") as mock_restart,
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()

        code = reembed_main(["--rebuild-fts"])

        assert code == EXIT_OK
        mock_stop.assert_not_called()
        mock_restart.assert_not_called()


def test_reembed_restart_on_error(tmp_path: Path) -> None:
    """Service is restarted even when reembed fails (DB error)."""
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=True),
        patch("skillsmith.reembed.cli._stop_service", return_value=True),
        patch("skillsmith.reembed.cli._restart_service") as mock_restart,
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()
        # Simulate FTS rebuild failure
        mock_vs.rebuild_fts_index.side_effect = Exception("DB error")

        code = reembed_main(["--rebuild-fts"])

        # Still exits OK (FTS failure is non-fatal)
        assert code == EXIT_OK
        # But service is still restarted
        mock_restart.assert_called_once()


# ---------------------------------------------------------------------------
# macOS launchctl PID parsing
# ---------------------------------------------------------------------------


def test_is_service_running_macos_with_pid() -> None:
    """_is_service_running returns True when launchctl list shows a real PID."""
    from skillsmith.reembed.cli import _is_service_running  # pyright: ignore[reportPrivateUsage]

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "12345\t0\tai.skillsmith\n"

    with (
        patch("platform.system", return_value="Darwin"),
        patch("shutil.which", return_value="/bin/launchctl"),
        patch("pathlib.Path.exists", return_value=True),
        patch("subprocess.run", return_value=mock_result),
    ):
        assert _is_service_running() is True


def test_is_service_running_macos_not_running() -> None:
    """_is_service_running returns False when launchctl list shows PID='-'."""
    from skillsmith.reembed.cli import _is_service_running  # pyright: ignore[reportPrivateUsage]

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "-\t0\tai.skillsmith\n"

    with (
        patch("platform.system", return_value="Darwin"),
        patch("shutil.which", return_value="/bin/launchctl"),
        patch("pathlib.Path.exists", return_value=True),
        patch("subprocess.run", return_value=mock_result),
    ):
        assert _is_service_running() is False


# ---------------------------------------------------------------------------
# Dry-run with service running
# ---------------------------------------------------------------------------


def test_reembed_dry_run_stops_service(tmp_path: Path) -> None:
    """--dry-run still stops the service to avoid DB lock conflicts."""
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=True),
        patch("skillsmith.reembed.cli._stop_service", return_value=True) as mock_stop,
        patch("skillsmith.reembed.cli._restart_service") as mock_restart,
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()

        code = reembed_main(["--dry-run"])

        assert code == EXIT_OK
        mock_stop.assert_called_once()
        mock_restart.assert_called_once()


# ---------------------------------------------------------------------------
# FTS rebuild warning includes remediation hint
# ---------------------------------------------------------------------------


def test_fts_rebuild_warning_includes_hint(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """FTS rebuild failure warning includes actionable remediation hint."""
    with (
        patch("skillsmith.reembed.cli.LadybugStore") as mock_store_cls,
        patch("skillsmith.reembed.cli.open_or_create") as mock_vs_cls,
        patch("skillsmith.reembed.cli.get_settings") as mock_settings,
        patch("skillsmith.reembed.cli._is_service_running", return_value=False),
    ):
        mock_settings.return_value.ladybug_db_path = str(tmp_path / "ladybug.db")
        mock_settings.return_value.runtime_embedding_model = "test-model"

        mock_store = MagicMock()
        mock_store_cls.return_value.__enter__ = MagicMock(return_value=mock_store)
        mock_store_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_store.execute.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value.__enter__ = MagicMock(return_value=mock_vs)
        mock_vs_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_vs.count_embeddings.return_value = 100
        mock_vs.fragment_ids_present.return_value = set()
        mock_vs.rebuild_fts_index.side_effect = Exception("stopwords has been deleted")

        with caplog.at_level(logging.WARNING):
            code = reembed_main(["--rebuild-fts"])

        assert code == EXIT_OK
        assert "BM25 leg degraded" in caplog.text
        assert "re-run" in caplog.text or "rebuild-fts" in caplog.text
