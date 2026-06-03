# Changelog

All notable changes to this project will be documented in this file.

## [0.0.1.0] - 2026-06-03

### Security

- **Path traversal fix in hook endpoint** — `POST /v1/hook/post-tool-use` now
  validates `tool_path` using `safe_contract_path()` before reading any file.
  Previously a substring check (`".agentalloy/contracts/" in tool_path`) could
  be bypassed with `../` sequences, allowing unauthenticated reads of arbitrary
  files. The endpoint is unauthenticated and the container binds `0.0.0.0:47950`.

- **Container runs as non-root** — the production `Containerfile` now creates
  `appuser` (UID 1001) and sets `USER appuser` before the entrypoint. Previously
  the service ran as root, amplifying any file-read vulnerability. `compose.yaml`
  adds `user: "1001:0"` to the long-running service and the init service handles
  volume ownership via `chown -R 1001:0 /app/data` before running migrations.

- **CI actions SHA-pinned** — `astral-sh/setup-uv` and `actions/checkout` are now
  pinned to immutable commit SHAs in `.github/workflows/ci.yml`. Mutable tags
  (`v3`, `v4`) allow supply-chain compromise via force-push to the upstream repo.

### Changed

- `.gitignore` — added `.gstack/` so local security audit reports (`/cso` output)
  are never accidentally committed to the open-source repository.
