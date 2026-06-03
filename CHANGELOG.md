# Changelog

All notable changes to this project will be documented in this file.

## [0.0.2.0] - 2026-06-03

### Added

- **Container lifecycle sentinel** — `install-packs` no longer triggers N
  stop/restart cycles when calling `ingest` subprocesses. `AGENTALLOY_DB_LOCK_HELD`
  env var acts as a reentrancy guard: set after confirming the uvicorn process
  exists, cleared before the child env is copied for restart. Child ingest
  processes inherit via POSIX env and short-circuit their own stop attempt.

- **`_run_container_guard()`** — new function owning the full stop/restart
  lifecycle for one `install-packs` invocation: single stop, all pack ingests
  with `no_restart=True`, single bulk reembed, single restart.

- **Embedding dimension guard** — `open_or_create()` raises `EmbeddingDimMismatch`
  at startup if the corpus was built at a different dimension than `EMBEDDING_DIM`
  (1024). Fail-fast prevents silent mid-request crashes when upgrading from
  `embeddinggemma` (768-dim) to `qwen3-embedding:0.6b` (1024-dim). Includes a
  `reembed --force` remediation message.

- **`_find_uvicorn_pid()` fix** — collects all matching PIDs, returns `min()`
  (parent process). `iterdir()` is not PID order; first-match could signal a
  worker rather than the parent holding the file lock.

- **`test_kuzu_lock_released()` container path fix** — reads `LADYBUG_DB_PATH`
  env var first (set by `compose.yaml`); falls back to `user_data_dir()` for
  native installs. Fixes silent skip of the lock check inside containers.

### Changed

- **Embedding model presets** — all `.env.*` platform presets updated from
  `embeddinggemma` (768-dim) to `qwen3-embedding:0.6b` (1024-dim). `.env.strix-point`
  excluded pending a 1024-dim model for the AMD Strix Point NPU backend.

- **`migrate.py`** — catches `EmbeddingDimMismatch`, prints remediation, exits 0.
  Allows `docker compose up` to complete init and start the main service rather
  than blocking at the migration step.
