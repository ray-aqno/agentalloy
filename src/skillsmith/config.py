"""Runtime configuration loaded from environment."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _user_corpus_dir() -> Path:
    """Default corpus location (XDG data dir). Mirrors install.state.corpus_dir.

    Duplicated here so the runtime service has no dependency on the install
    module — `config` is imported by every part of the service.

    Resolved per-call (not cached) so a process that adjusts XDG_DATA_HOME
    after import (e.g. tests) sees the correct location.
    """
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "skillsmith" / "corpus"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # No env_file — config comes from process environment. The
        # user-scoped .env produced by `write-env` lives at
        # `${XDG_CONFIG_HOME}/skillsmith/.env`; operators source it into
        # the service's process env (or a `skillsmith serve` wrapper does
        # it for them). A project-local `.env` in cwd is intentionally
        # NOT loaded — Skillsmith state is user-scoped, not per-repo.
        extra="ignore",
    )

    # `default_factory` defers evaluation to instantiation time so a
    # process that sets XDG_DATA_HOME after `skillsmith.config` is
    # imported (or in test environments that monkeypatch the env var)
    # gets the correct path. With a plain `default=...` the path would
    # be frozen at module import.
    ladybug_db_path: str = Field(default_factory=lambda: str(_user_corpus_dir() / "ladybug"))
    duckdb_path: str = Field(default_factory=lambda: str(_user_corpus_dir() / "skills.duck"))
    log_level: str = "INFO"

    # Authoring pipeline (separate from runtime retrieval above). LM Studio
    # hosts generation and embeddings via its OpenAI-compatible endpoint.
    # Override via .env if you later split embeddings to FastFlowLM or similar.
    lm_studio_base_url: str = "http://localhost:1234"
    authoring_embed_base_url: str = "http://localhost:1234"
    # Both roles use Qwen3.6-35B-A3B. MoE activates ~3B params per token so
    # throughput is closer to a 3B dense model than to 14B dense. Author
    # prompts include ``/no_think`` to suppress the reasoning loop (see
    # authoring.driver); Critic prompts keep thinking enabled because
    # dedup + effectiveness judgment benefits from it.
    authoring_model: str = "qwen/qwen3.6-35b-a3b"
    critic_model: str = "qwen/qwen3.6-35b-a3b"
    authoring_embedding_model: str = "text-embedding-nomic-embed-text-v1.5"

    # Runtime serving (retrieve / compose). Per v5.4 brief, the runtime path
    # holds zero generative LLM dependency — only an embedding service. The
    # NPU-resident Embedding-Gemma-300M is served by FastFlowLM at the OpenAI-
    # compatible endpoint below. The inference model on the iGPU calls the
    # skill API and assembles fragments in its own context.
    runtime_embed_base_url: str = "http://127.0.0.1:52625"
    runtime_embedding_model: str = "embed-gemma:300m"
    dedup_hard_threshold: float = 0.92
    dedup_soft_threshold: float = 0.80
    bounce_budget: int = 3

    def ensure_data_dirs(self) -> None:
        """Create parent directories for LadybugDB and DuckDB if missing."""
        Path(self.ladybug_db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.duckdb_path).parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Load settings and log which values came from defaults."""
    s = Settings()
    for field in Settings.model_fields:
        source = "env" if field.upper() in _env_keys() else "default"
        logger.debug("config %s=%r source=%s", field, getattr(s, field), source)
    return s


def _env_keys() -> set[str]:
    return set(os.environ.keys())
