"""Migration CLI: ``python -m skillsmith.migrate``.

Creates the LadybugDB graph store and the DuckDB vector + telemetry store
at the paths configured via environment. Safe to run multiple times
(idempotent).
"""

from __future__ import annotations

import logging
import sys

from skillsmith.config import get_settings
from skillsmith.storage.ladybug import LadybugStore
from skillsmith.storage.vector_store import open_or_create

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    settings.ensure_data_dirs()

    logger.info("migrate ladybug path=%s", settings.ladybug_db_path)
    with LadybugStore(settings.ladybug_db_path) as store:
        store.migrate()

    logger.info("migrate duckdb path=%s", settings.duckdb_path)
    with open_or_create(settings.duckdb_path):
        # open_or_create runs the schema DDL; closing the connection is sufficient.
        pass

    logger.info("migrate ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
