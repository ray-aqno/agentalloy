"""Fixture loader CLI: ``python -m skillsmith.fixtures load``."""

from __future__ import annotations

import argparse
import logging
import sys

from skillsmith.config import get_settings
from skillsmith.fixtures.loader import load_fixtures
from skillsmith.storage.ladybug import LadybugStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skillsmith.fixtures")
    parser.add_argument("command", choices=["load"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    settings = get_settings()
    settings.ensure_data_dirs()

    if args.command == "load":
        with LadybugStore(settings.ladybug_db_path) as store:
            load_fixtures(store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
