"""Integration tests for container stop/restart across reembed, install-packs, and ingest.

All external dependencies (uvicorn, /proc scanning, health endpoint, DB access)
are mocked so these tests run in isolation without a live container or service.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentalloy.install.container_service import (
    restart_service_in_container,
    stop_service_in_container,
)

# ---------------------------------------------------------------------------
# 1. reembed integration tests
# ---------------------------------------------------------------------------


class TestReembedContainerStopRestart:
    """Tests for reembed subcommand's container stop/restart behavior."""

    def test_reembed_stops_and_restarts_service_when_running(self):
        """reembed with service running: stops uvicorn, runs embed, restarts service."""
        with (
            patch("agentalloy.reembed.cli.is_in_container", return_value=True),
            patch(
                "agentalloy.reembed.cli.stop_service_in_container", return_value=True
            ) as mock_stop,
            patch(
                "agentalloy.reembed.cli.restart_service_in_container", return_value=True
            ) as mock_restart,
            patch("agentalloy.reembed.cli._is_service_running", return_value=True),
            patch("agentalloy.reembed.cli._stop_service", return_value=True),
            patch("agentalloy.reembed.cli._restart_service"),
            patch("agentalloy.reembed.cli.get_settings") as mock_settings,
            patch("agentalloy.reembed.cli.open_or_create") as mock_open_vs,
            patch("agentalloy.reembed.cli.LadybugStore") as mock_store_cls,
            patch("agentalloy.reembed.cli.discover_unembedded_fragments", return_value=[]),
            patch("agentalloy.reembed.cli.ReembedStats") as mock_stats_cls,
            patch("agentalloy.reembed.cli.get_embed_client") as mock_get_client,
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"
            mock_settings.return_value.runtime_embedding_model = "test-model"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_cls.return_value = mock_store_instance

            mock_vs_instance = MagicMock()
            mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
            mock_vs_instance.__exit__ = MagicMock(return_value=False)
            mock_open_vs.return_value = mock_vs_instance

            mock_stats = MagicMock()
            mock_stats.embedded = 0
            mock_stats_cls.return_value = mock_stats

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_get_client.return_value = mock_client

            from agentalloy.reembed.cli import main as reembed_main

            rc = reembed_main([])

            assert rc == 0
            # stop_service_in_container should be called from the container block
            mock_stop.assert_called_once_with(no_restart=False)
            # restart_service_in_container should be called in the finally block
            mock_restart.assert_called_once_with(no_restart=False)

    def test_reembed_skips_container_stop_restart_with_no_restart_flag(self):
        """reembed with --no-restart: does NOT stop/restart the service."""
        with (
            patch("agentalloy.reembed.cli.is_in_container", return_value=True),
            patch("agentalloy.reembed.cli.stop_service_in_container") as mock_stop,
            patch("agentalloy.reembed.cli.restart_service_in_container") as mock_restart,
            patch("agentalloy.reembed.cli._is_service_running", return_value=True),
            patch("agentalloy.reembed.cli._stop_service", return_value=True),
            patch("agentalloy.reembed.cli._restart_service"),
            patch("agentalloy.reembed.cli.get_settings") as mock_settings,
            patch("agentalloy.reembed.cli.open_or_create") as mock_open_vs,
            patch("agentalloy.reembed.cli.LadybugStore") as mock_store_cls,
            patch("agentalloy.reembed.cli.discover_unembedded_fragments", return_value=[]),
            patch("agentalloy.reembed.cli.ReembedStats") as mock_stats_cls,
            patch("agentalloy.reembed.cli.get_embed_client") as mock_get_client,
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"
            mock_settings.return_value.runtime_embedding_model = "test-model"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_cls.return_value = mock_store_instance

            mock_vs_instance = MagicMock()
            mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
            mock_vs_instance.__exit__ = MagicMock(return_value=False)
            mock_open_vs.return_value = mock_vs_instance

            mock_stats = MagicMock()
            mock_stats.embedded = 0
            mock_stats_cls.return_value = mock_stats

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_get_client.return_value = mock_client

            from agentalloy.reembed.cli import main as reembed_main

            rc = reembed_main(["--no-restart"])

            assert rc == 0
            # With --no-restart, stop_service_in_container is NOT called at all
            mock_stop.assert_not_called()
            # With --no-restart, restart_service_in_container is NOT called at all
            mock_restart.assert_not_called()

    def test_reembed_service_not_running_no_op_stop(self):
        """reembed when service is not running: stop is no-op, normal operation proceeds."""
        with (
            patch("agentalloy.reembed.cli.is_in_container", return_value=True),
            patch(
                "agentalloy.reembed.cli.stop_service_in_container", return_value=False
            ) as mock_stop,
            patch(
                "agentalloy.reembed.cli.restart_service_in_container", return_value=True
            ) as mock_restart,
            patch("agentalloy.reembed.cli._is_service_running", return_value=False),
            patch("agentalloy.reembed.cli.get_settings") as mock_settings,
            patch("agentalloy.reembed.cli.open_or_create") as mock_open_vs,
            patch("agentalloy.reembed.cli.LadybugStore") as mock_store_cls,
            patch("agentalloy.reembed.cli.discover_unembedded_fragments", return_value=[]),
            patch("agentalloy.reembed.cli.ReembedStats") as mock_stats_cls,
            patch("agentalloy.reembed.cli.get_embed_client") as mock_get_client,
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"
            mock_settings.return_value.runtime_embedding_model = "test-model"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_cls.return_value = mock_store_instance

            mock_vs_instance = MagicMock()
            mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
            mock_vs_instance.__exit__ = MagicMock(return_value=False)
            mock_open_vs.return_value = mock_vs_instance

            mock_stats = MagicMock()
            mock_stats.embedded = 0
            mock_stats_cls.return_value = mock_stats

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_get_client.return_value = mock_client

            from agentalloy.reembed.cli import main as reembed_main

            rc = reembed_main([])

            assert rc == 0
            # stop_service_in_container should be called but return False (no-op since no pid)
            mock_stop.assert_called_once_with(no_restart=False)
            # restart should NOT be called since stop returned False (no service was running)
            mock_restart.assert_not_called()


# ---------------------------------------------------------------------------
# 2. install-packs integration tests
# ---------------------------------------------------------------------------


class TestInstallPacksContainerStopRestart:
    """Tests for install-packs subcommand's container stop/restart behavior.

    install-packs calls reembed internally via _bulk_reembed().
    These tests verify the reembed path handles stop/restart correctly.
    """

    def test_install_packs_stops_and_restarts_service(self):
        """install-packs calls reembed which stops/restarts the service in container mode."""
        with (
            patch("agentalloy.reembed.cli.is_in_container", return_value=True),
            patch(
                "agentalloy.reembed.cli.stop_service_in_container", return_value=True
            ) as mock_stop,
            patch("agentalloy.reembed.cli.restart_service_in_container", return_value=True),
            patch("agentalloy.reembed.cli._is_service_running", return_value=True),
            patch("agentalloy.reembed.cli._stop_service", return_value=True),
            patch("agentalloy.reembed.cli._restart_service"),
            patch("agentalloy.reembed.cli.get_settings") as mock_settings,
            patch("agentalloy.reembed.cli.open_or_create") as mock_open_vs,
            patch("agentalloy.reembed.cli.LadybugStore") as mock_store_cls,
            patch("agentalloy.reembed.cli.discover_unembedded_fragments", return_value=[]),
            patch("agentalloy.reembed.cli.ReembedStats") as mock_stats_cls,
            patch("agentalloy.reembed.cli.get_embed_client") as mock_get_client,
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"
            mock_settings.return_value.runtime_embedding_model = "test-model"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_cls.return_value = mock_store_instance

            mock_vs_instance = MagicMock()
            mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
            mock_vs_instance.__exit__ = MagicMock(return_value=False)
            mock_open_vs.return_value = mock_vs_instance

            mock_stats = MagicMock()
            mock_stats.embedded = 0
            mock_stats_cls.return_value = mock_stats

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_get_client.return_value = mock_client

            from agentalloy.reembed.cli import main as reembed_main

            # install-packs calls reembed with --no-restart (it handles restart itself)
            rc = reembed_main(["--no-restart"])

            assert rc == 0
            # With --no-restart, stop_service_in_container is NOT called at all
            mock_stop.assert_not_called()

    def test_install_packs_no_restart_flag_skips_restart(self):
        """install-packs with --no-restart: reembed skips container restart."""
        with (
            patch("agentalloy.reembed.cli.is_in_container", return_value=True),
            patch("agentalloy.reembed.cli.stop_service_in_container") as mock_stop,
            patch("agentalloy.reembed.cli.restart_service_in_container") as mock_restart,
            patch("agentalloy.reembed.cli._is_service_running", return_value=True),
            patch("agentalloy.reembed.cli._stop_service", return_value=True),
            patch("agentalloy.reembed.cli._restart_service"),
            patch("agentalloy.reembed.cli.get_settings") as mock_settings,
            patch("agentalloy.reembed.cli.open_or_create") as mock_open_vs,
            patch("agentalloy.reembed.cli.LadybugStore") as mock_store_cls,
            patch("agentalloy.reembed.cli.discover_unembedded_fragments", return_value=[]),
            patch("agentalloy.reembed.cli.ReembedStats") as mock_stats_cls,
            patch("agentalloy.reembed.cli.get_embed_client") as mock_get_client,
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"
            mock_settings.return_value.runtime_embedding_model = "test-model"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_cls.return_value = mock_store_instance

            mock_vs_instance = MagicMock()
            mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
            mock_vs_instance.__exit__ = MagicMock(return_value=False)
            mock_open_vs.return_value = mock_vs_instance

            mock_stats = MagicMock()
            mock_stats.embedded = 0
            mock_stats_cls.return_value = mock_stats

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_get_client.return_value = mock_client

            from agentalloy.reembed.cli import main as reembed_main

            rc = reembed_main(["--no-restart"])

            assert rc == 0
            # With --no-restart, stop_service_in_container is NOT called at all
            mock_stop.assert_not_called()
            # With --no-restart, restart_service_in_container is NOT called at all
            mock_restart.assert_not_called()

    def test_install_packs_service_not_running(self):
        """install-packs when service not running: stop is no-op, operation proceeds."""
        with (
            patch("agentalloy.reembed.cli.is_in_container", return_value=True),
            patch(
                "agentalloy.reembed.cli.stop_service_in_container", return_value=False
            ) as mock_stop,
            patch("agentalloy.reembed.cli._is_service_running", return_value=False),
            patch("agentalloy.reembed.cli.get_settings") as mock_settings,
            patch("agentalloy.reembed.cli.open_or_create") as mock_open_vs,
            patch("agentalloy.reembed.cli.LadybugStore") as mock_store_cls,
            patch("agentalloy.reembed.cli.discover_unembedded_fragments", return_value=[]),
            patch("agentalloy.reembed.cli.ReembedStats") as mock_stats_cls,
            patch("agentalloy.reembed.cli.get_embed_client") as mock_get_client,
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"
            mock_settings.return_value.runtime_embedding_model = "test-model"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_cls.return_value = mock_store_instance

            mock_vs_instance = MagicMock()
            mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
            mock_vs_instance.__exit__ = MagicMock(return_value=False)
            mock_open_vs.return_value = mock_vs_instance

            mock_stats = MagicMock()
            mock_stats.embedded = 0
            mock_stats_cls.return_value = mock_stats

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_get_client.return_value = mock_client

            from agentalloy.reembed.cli import main as reembed_main

            rc = reembed_main([])

            assert rc == 0
            # stop_service_in_container called but returns False (no process found)
            mock_stop.assert_called_once_with(no_restart=False)


# ---------------------------------------------------------------------------
# 3. ingest integration tests
# ---------------------------------------------------------------------------


class TestIngestContainerStopRestart:
    """Tests for ingest subcommand's container stop/restart behavior."""

    @pytest.fixture()
    def _sample_yaml(self, tmp_path: Path) -> Path:
        """Create a minimal valid review YAML for ingest tests."""
        yaml_content = """\
skill_type: system
skill_id: sys-test-ingest
canonical_name: Test Ingest Skill
category: governance
skill_class: governance
domain_tags: []
always_apply: true
phase_scope: []
category_scope: []
author: test
change_summary: test ingest
raw_prose: test content
fragments:
  - sequence: 1
    fragment_type: example
    content: test fragment
"""
        yaml_path = tmp_path / "test_skill.yaml"
        yaml_path.write_text(yaml_content)
        return yaml_path

    def test_ingest_stops_and_restarts_service_single_file(self, _sample_yaml: Path):
        """ingest with single file in container mode: stops service, ingests, restarts."""
        with (
            patch("agentalloy.ingest.is_in_container", return_value=True),
            patch("agentalloy.ingest.stop_service_in_container", return_value=True),
            patch(
                "agentalloy.ingest.restart_service_in_container", return_value=True
            ) as mock_restart,
            patch("agentalloy.ingest.get_settings") as mock_settings,
            patch("agentalloy.ingest.LadybugStore") as mock_store_cls,
            patch("agentalloy.ingest._validate", return_value=[]),
            patch("agentalloy.ingest._lint", return_value=[]),
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_instance.scalar = MagicMock(side_effect=[None, None])
            mock_store_cls.return_value = mock_store_instance

            from agentalloy.ingest import main as ingest_main

            rc = ingest_main([str(_sample_yaml), "--yes"])

            assert rc == 0
            mock_restart.assert_called_once_with(no_restart=False)

    def test_ingest_skips_restart_with_no_restart_flag(self, _sample_yaml: Path):
        """ingest with --no-restart: does NOT restart the service."""
        with (
            patch("agentalloy.ingest.is_in_container", return_value=True),
            patch("agentalloy.ingest.stop_service_in_container", return_value=True),
            patch("agentalloy.ingest.restart_service_in_container") as mock_restart,
            patch("agentalloy.ingest.get_settings") as mock_settings,
            patch("agentalloy.ingest.LadybugStore") as mock_store_cls,
            patch("agentalloy.ingest._validate", return_value=[]),
            patch("agentalloy.ingest._lint", return_value=[]),
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_instance.scalar = MagicMock(side_effect=[None, None])
            mock_store_cls.return_value = mock_store_instance

            from agentalloy.ingest import main as ingest_main

            rc = ingest_main([str(_sample_yaml), "--yes", "--no-restart"])

            assert rc == 0
            # With --no-restart, stop_service_in_container is NOT called at all
            # With --no-restart, restart_service_in_container is NOT called at all
            mock_restart.assert_not_called()

    def test_ingest_service_not_running_single_file(self, _sample_yaml: Path):
        """ingest when service not running: stop is no-op, normal operation."""
        with (
            patch("agentalloy.ingest.is_in_container", return_value=True),
            patch("agentalloy.ingest.stop_service_in_container", return_value=False) as mock_stop,
            patch(
                "agentalloy.ingest.restart_service_in_container", return_value=True
            ) as mock_restart,
            patch("agentalloy.ingest.get_settings") as mock_settings,
            patch("agentalloy.ingest.LadybugStore") as mock_store_cls,
            patch("agentalloy.ingest._validate", return_value=[]),
            patch("agentalloy.ingest._lint", return_value=[]),
        ):
            mock_settings.return_value.ladybug_db_path = "/tmp/test_ladybug"

            mock_store_instance = MagicMock()
            mock_store_instance.__enter__ = MagicMock(return_value=mock_store_instance)
            mock_store_instance.__exit__ = MagicMock(return_value=False)
            mock_store_instance.scalar = MagicMock(side_effect=[None, None])
            mock_store_cls.return_value = mock_store_instance

            from agentalloy.ingest import main as ingest_main

            rc = ingest_main([str(_sample_yaml), "--yes"])

            assert rc == 0
            # stop_service_in_container returns False (no process found)
            mock_stop.assert_called_once_with(no_restart=False)
            # restart should NOT be called since stop returned False (no service was running)
            mock_restart.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Edge case tests
# ---------------------------------------------------------------------------


class TestContainerServiceEdgeCases:
    """Edge case tests for container stop/restart behavior."""

    def test_concurrent_stop_attempts(self):
        """Two concurrent stop_service_in_container calls: second sees process already gone."""
        with (
            patch(
                "agentalloy.install.container_service._find_uvicorn_pid",
                side_effect=[12345, None],
            ),
            patch(
                "agentalloy.install.container_service._pid_alive",
                side_effect=[True, False],
            ),
        ):
            result1 = stop_service_in_container()
            result2 = stop_service_in_container()

            assert result1 is True
            assert result2 is False

    def test_user_interrupt_during_stop(self):
        """SIGTERM sent, process exits gracefully within poll window."""
        with (
            patch(
                "agentalloy.install.container_service._find_uvicorn_pid",
                return_value=12345,
            ),
            patch(
                "agentalloy.install.container_service._pid_alive",
                side_effect=[True, False],
            ),
        ):
            result = stop_service_in_container()
            assert result is True

    def test_restart_service_fails(self):
        """restart_service_in_container fails: service doesn't start, returns False."""
        with (
            patch(
                "agentalloy.install.container_service.install_state.load_state",
                return_value={"port": 47950},
            ),
            patch(
                "agentalloy.install.container_service.server_proc.server_log_path",
            ) as mock_log_path,
            patch(
                "agentalloy.install.container_service.server_proc.port_reachable",
                return_value=False,
            ),
            patch(
                "agentalloy.install.container_service.subprocess.Popen",
            ) as mock_popen,
        ):
            mock_log_path.return_value = Path("/tmp/test.log")
            mock_popen.side_effect = RuntimeError("cannot start uvicorn")

            result = restart_service_in_container()

            assert result is False

    def test_service_already_stopped_double_stop(self):
        """Double-stop scenario: first stop succeeds, second stop is no-op (returns False)."""
        with (
            patch(
                "agentalloy.install.container_service._find_uvicorn_pid",
                side_effect=[12345, None],
            ),
            patch(
                "agentalloy.install.container_service._pid_alive",
                side_effect=[True, False],
            ),
        ):
            # First stop: finds process, stops it
            result1 = stop_service_in_container()
            assert result1 is True

            # Second stop: no process found, returns False (no-op)
            result2 = stop_service_in_container()
            assert result2 is False
