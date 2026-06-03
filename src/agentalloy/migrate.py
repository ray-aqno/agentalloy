"""Migration CLI: ``python -m agentalloy.migrate``.

Creates the LadybugDB graph store and the DuckDB vector + telemetry store
at the paths configured via environment. Safe to run multiple times
(idempotent).
"""

from __future__ import annotations

import logging
import sys

from agentalloy.config import get_settings
from agentalloy.storage.ladybug import LadybugStore
from agentalloy.storage.vector_store import EmbeddingDimMismatch, open_or_create

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    settings.ensure_data_dirs()

    logger.info("migrate ladybug path=%s", settings.ladybug_db_path)
    with LadybugStore(settings.ladybug_db_path) as store:
        store.migrate()

    logger.info("migrate duckdb path=%s", settings.duckdb_path)
    try:
        with open_or_create(settings.duckdb_path):
            # open_or_create runs the schema DDL; closing the connection is sufficient.
            pass
    except EmbeddingDimMismatch as exc:
        # Existing corpus was built with a different embedding model (e.g. embeddinggemma
        # 768-dim vs qwen3-embedding:0.6b 1024-dim). Migration schema is fine; the user
        # must reembed before the service can serve queries. Exit 0 so compose lets the
        # main service start — it will surface the same error on its first open_or_create.
        print(str(exc), file=sys.stderr)
        print(
            "[migrate] WARNING: schema migration succeeded but corpus dimension mismatch detected.",
            file=sys.stderr,
        )
        logger.info("migrate ok (dim mismatch — main service will surface remediation on startup)")
        return 0

    logger.info("migrate ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
