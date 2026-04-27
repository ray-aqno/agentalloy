"""Per-test isolation for the install module's user-scoped state.

State (`install-state.json`), `.env`, and the corpus all live under the
XDG dirs as of schema v2. Without this fixture every test would read and
write the real `~/.config/skillsmith/` and `~/.local/share/skillsmith/`,
polluting the user's install state and producing flaky tests.

Autouse: every test in `tests/install/` gets fresh XDG dirs pointing at
its own `tmp_path` automatically.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_install_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect XDG config/data dirs to per-test tmp dirs."""
    config_home = tmp_path / "_xdg_config"
    data_home = tmp_path / "_xdg_data"
    config_home.mkdir(parents=True, exist_ok=True)
    data_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
