# ruff: noqa: I001 -- testing private module members intentionally
"""Tests for install state schema migration (v3 → v4)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


from agentalloy.install import state as install_state

# Local aliases for private helpers
_empty_state = install_state._empty_state  # pyright: ignore[reportPrivateUsage]


class TestSchemaVersion:
    """Test CURRENT_SCHEMA_VERSION is 4."""

    def test_schema_version_is_4(self):
        assert install_state.CURRENT_SCHEMA_VERSION == 4


class TestFreshStateV4:
    """Test _empty_state() returns schema v4 with runtime fields."""

    def test_fresh_state_has_runtime_fields(self):
        st = _empty_state()
        assert st["schema_version"] == 4
        # New runtime fields present
        assert "runtime_binary" in st
        assert "image_tag" in st
        assert "container_name" in st
        assert "data_volume" in st
        # Compose fields removed
        assert "compose_file" not in st
        assert "compose_binary" not in st
        assert "compose_binary_path" not in st

    def test_fresh_state_preserves_common_fields(self):
        st = _empty_state()
        assert "install_started_at" in st
        assert st["completed_steps"] == []
        assert st["harness_files_written"] == []
        assert st["models_pulled"] == []
        assert st["port"] == 47950
        assert st["last_verify_passed_at"] is None
        assert st["pending_pack_selection"] is None
        assert "deployment" in st


class TestV3ToV4Migration:
    """Test that v3 state files are migrated to v4 on load."""

    def test_v3_migrated_to_v4(self, tmp_path: Path):
        """A v3 state file loads with compose fields removed and runtime fields added."""
        config_dir = tmp_path / ".config"
        data_dir = tmp_path / ".local" / "share"
        config_dir.mkdir(parents=True)
        data_dir.mkdir(parents=True)
        old_config = os.environ.get("XDG_CONFIG_HOME")
        old_data = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(config_dir)
        os.environ["XDG_DATA_HOME"] = str(data_dir)

        try:
            agentalloy_dir = config_dir / "agentalloy"
            agentalloy_dir.mkdir(parents=True)
            state_file = agentalloy_dir / "install-state.json"
            v3_state: dict[str, Any] = {
                "schema_version": 3,
                "install_started_at": "2025-01-01T00:00:00",
                "completed_steps": [],
                "harness_files_written": [],
                "models_pulled": [],
                "env_path": None,
                "port": 47950,
                "last_verify_passed_at": None,
                "pending_pack_selection": None,
                "deployment": "container",
                "compose_file": "/home/user/project/compose.yaml",
                "compose_binary": "podman compose",
                "compose_binary_path": "/usr/bin/podman",
            }
            state_file.write_text(json.dumps(v3_state))

            import importlib

            importlib.reload(install_state)
            st = install_state.load_state()

            # Schema version bumped
            assert st["schema_version"] == 4
            # Compose fields removed
            assert "compose_file" not in st
            assert "compose_binary" not in st
            assert "compose_binary_path" not in st
            # Runtime fields added
            assert "runtime_binary" in st
            assert "image_tag" in st
            assert "container_name" in st
            assert "data_volume" in st
            # deployment preserved
            assert st["deployment"] == "container"

        finally:
            if old_config is not None:
                os.environ["XDG_CONFIG_HOME"] = old_config
            elif "XDG_CONFIG_HOME" in os.environ:
                del os.environ["XDG_CONFIG_HOME"]
            if old_data is not None:
                os.environ["XDG_DATA_HOME"] = old_data
            elif "XDG_DATA_HOME" in os.environ:
                del os.environ["XDG_DATA_HOME"]

    def test_v3_preserves_existing_fields(self, tmp_path: Path):
        """Migration preserves existing v3 fields while adding v4 fields and removing compose fields."""
        config_dir = tmp_path / ".config"
        data_dir = tmp_path / ".local" / "share"
        config_dir.mkdir(parents=True)
        data_dir.mkdir(parents=True)
        old_config = os.environ.get("XDG_CONFIG_HOME")
        old_data = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(config_dir)
        os.environ["XDG_DATA_HOME"] = str(data_dir)

        try:
            agentalloy_dir = config_dir / "agentalloy"
            agentalloy_dir.mkdir(parents=True)
            state_file = agentalloy_dir / "install-state.json"
            v3_state: dict[str, Any] = {
                "schema_version": 3,
                "install_started_at": "2025-01-01T00:00:00",
                "completed_steps": [
                    {"step": "wire-harness", "completed_at": "2025-01-01T00:01:00"}
                ],
                "harness_files_written": [],
                "models_pulled": ["ollama:nomic-embed-text"],
                "env_path": None,
                "port": 50000,
                "last_verify_passed_at": "2025-01-01T00:02:00",
                "pending_pack_selection": ["core"],
                "deployment": "container",
                "compose_file": "/home/user/compose.yaml",
                "compose_binary": "docker compose",
                "compose_binary_path": "/usr/bin/docker",
            }
            state_file.write_text(json.dumps(v3_state))

            import importlib

            importlib.reload(install_state)
            st = install_state.load_state()

            # Existing fields preserved
            assert st["port"] == 50000
            assert st["completed_steps"] == v3_state["completed_steps"]
            assert st["models_pulled"] == ["ollama:nomic-embed-text"]
            assert st["pending_pack_selection"] == ["core"]
            assert st["last_verify_passed_at"] == "2025-01-01T00:02:00"
            # deployment preserved
            assert st["deployment"] == "container"
            # Compose fields removed
            assert "compose_file" not in st
            assert "compose_binary" not in st
            assert "compose_binary_path" not in st
            # Runtime fields added
            assert "runtime_binary" in st
            assert "image_tag" in st
            assert "container_name" in st
            assert "data_volume" in st

        finally:
            if old_config is not None:
                os.environ["XDG_CONFIG_HOME"] = old_config
            elif "XDG_CONFIG_HOME" in os.environ:
                del os.environ["XDG_CONFIG_HOME"]
            if old_data is not None:
                os.environ["XDG_DATA_HOME"] = old_data
            elif "XDG_DATA_HOME" in os.environ:
                del os.environ["XDG_DATA_HOME"]

    def test_v3_migrate_direct(self):
        """Test _migrate() directly for v3 → v4 transition."""
        v3_state: dict[str, Any] = {
            "schema_version": 3,
            "deployment": "container",
            "compose_file": "/test/compose.yaml",
            "compose_binary": "podman compose",
            "compose_binary_path": "/usr/bin/podman",
            "install_started_at": "2025-01-01T00:00:00",
            "completed_steps": [],
            "harness_files_written": [],
            "models_pulled": [],
            "env_path": None,
            "port": 47950,
            "last_verify_passed_at": None,
            "pending_pack_selection": None,
        }
        result = install_state._migrate(v3_state, 3)
        assert result["schema_version"] == 4
        assert "compose_file" not in result
        assert "compose_binary" not in result
        assert "compose_binary_path" not in result
        assert "runtime_binary" in result
        assert "image_tag" in result
        assert "container_name" in result
        assert "data_volume" in result
        assert result["deployment"] == "container"

    def test_v4_state_no_migration_needed(self, tmp_path: Path):
        """A v4 state file loads unchanged."""
        config_dir = tmp_path / ".config"
        data_dir = tmp_path / ".local" / "share"
        config_dir.mkdir(parents=True)
        data_dir.mkdir(parents=True)
        old_config = os.environ.get("XDG_CONFIG_HOME")
        old_data = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(config_dir)
        os.environ["XDG_DATA_HOME"] = str(data_dir)

        try:
            agentalloy_dir = config_dir / "agentalloy"
            agentalloy_dir.mkdir(parents=True)
            state_file = agentalloy_dir / "install-state.json"
            v4_state: dict[str, Any] = {
                "schema_version": 4,
                "install_started_at": "2025-01-01T00:00:00",
                "completed_steps": [],
                "harness_files_written": [],
                "models_pulled": [],
                "env_path": None,
                "port": 47950,
                "last_verify_passed_at": None,
                "pending_pack_selection": None,
                "deployment": "container",
                "runtime_binary": "podman",
                "image_tag": "agentalloy:latest",
                "container_name": "agentalloy",
                "data_volume": "agentalloy-data",
            }
            state_file.write_text(json.dumps(v4_state))

            import importlib

            importlib.reload(install_state)
            st = install_state.load_state()

            assert st["schema_version"] == 4
            assert st["runtime_binary"] == "podman"
            assert st["image_tag"] == "agentalloy:latest"
            assert st["container_name"] == "agentalloy"
            assert st["data_volume"] == "agentalloy-data"
            assert "compose_file" not in st
            assert "compose_binary" not in st
            assert "compose_binary_path" not in st

        finally:
            if old_config is not None:
                os.environ["XDG_CONFIG_HOME"] = old_config
            elif "XDG_CONFIG_HOME" in os.environ:
                del os.environ["XDG_CONFIG_HOME"]
            if old_data is not None:
                os.environ["XDG_DATA_HOME"] = old_data
            elif "XDG_DATA_HOME" in os.environ:
                del os.environ["XDG_DATA_HOME"]
