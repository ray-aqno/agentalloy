# Containerfile for the AgentAlloy service.
# Compatible with Podman (project preference) and Docker (works as Dockerfile via --file Containerfile).
#
# Build:  podman build -t agentalloy -f Containerfile .
# Run:    via compose.yaml (recommended) or `podman run --rm -p 47950:47950 -v ./data:/app/data agentalloy`

FROM python:3.12-slim AS base

# Install uv (Astral) and minimal runtime deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv is the project's package manager (matches host conventions)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first for layer-cache friendliness
COPY pyproject.toml uv.lock ./

# Install third-party deps without trying to build the project itself
# (needs README.md, src/, etc. — added in the next layer).
RUN uv sync --frozen --no-dev --no-install-project

# Copy the project source and README (used by hatchling for metadata),
# then install the project itself.
COPY README.md ./
COPY src/ ./src/

# Create an empty data dir so the image is runnable without a bind mount.
# The corpus (LadybugDB + DuckDB) is not shipped in the repo — it's
# generated locally on first install via `agentalloy install-packs` and
# `agentalloy.migrate`. compose.yaml bind-mounts a host volume onto
# /app/data so user data persists across container restarts.
RUN mkdir -p data

RUN uv sync --frozen --no-dev

ENV LADYBUG_DB_PATH=/app/data/ladybug \
    DUCKDB_PATH=/app/data/skills.duck \
    LOG_LEVEL=INFO

EXPOSE 47950

# Note: HEALTHCHECK is intentionally defined in compose.yaml rather than here.
# Podman's default OCI image format does not honor inline HEALTHCHECK directives;
# the compose-level healthcheck works on both Podman and Docker.

# Create non-root user. -g root: GID 0 so group-readable mounts remain accessible.
# chown -R: bounded by /app image layer contents (≤ wheel install + packs, O(thousands) files). P10-R2.
RUN useradd -r -u 1001 -g root appuser \
    && chown -R appuser /app

# uv writes cache/tmp to $HOME by default. Set HOME=/app so appuser (no home dir) can write.
ENV HOME=/app

USER appuser

CMD ["uv", "run", "uvicorn", "agentalloy.app:app", "--host", "0.0.0.0", "--port", "47950"]
