# Containerfile for the Skillsmith service.
# Compatible with Podman (project preference) and Docker (works as Dockerfile via --file Containerfile).
#
# Build:  podman build -t skillsmith -f Containerfile .
# Run:    via compose.yaml (recommended) or `podman run --rm -p 8000:8000 -v ./data:/app/data skillsmith`

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

# Copy the project source, README (used by hatchling for metadata), and the
# seeded corpus that ships in-repo. Then install the project itself.
COPY README.md ./
COPY src/ ./src/
COPY data/ ./data/

RUN uv sync --frozen --no-dev

# The data directory is bind-mounted at runtime (see compose.yaml) so user
# ingestions persist on the host. The COPY above provides a sane default
# for users running the image directly without compose.

ENV LADYBUG_DB_PATH=/app/data/ladybug \
    DUCKDB_PATH=/app/data/skills.duck \
    LOG_LEVEL=INFO

EXPOSE 8000

# Note: HEALTHCHECK is intentionally defined in compose.yaml rather than here.
# Podman's default OCI image format does not honor inline HEALTHCHECK directives;
# the compose-level healthcheck works on both Podman and Docker.

CMD ["uv", "run", "uvicorn", "skillsmith.app:app", "--host", "0.0.0.0", "--port", "8000"]
