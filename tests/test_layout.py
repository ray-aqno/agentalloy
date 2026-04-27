"""AC-4: new modules under src/skillsmith/ are picked up by pytest and pyright."""

from __future__ import annotations

import importlib


def test_package_importable() -> None:
    mod = importlib.import_module("skillsmith")
    assert hasattr(mod, "__version__")


def test_app_factory_importable() -> None:
    mod = importlib.import_module("skillsmith.app")
    assert callable(mod.create_app)
