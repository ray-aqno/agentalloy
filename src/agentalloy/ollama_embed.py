"""Ollama-native embedding client.

Uses Ollama's ``/api/embed`` endpoint (available since v0.1.32) instead of
the OpenAI-compatible ``/v1/embeddings`` path.  This lets the runtime
service talk directly to an Ollama instance without requiring the OpenAI
compat layer.

The interface mirrors the ``EmbedClient`` protocol so
the two can be swapped via the provider factory in ``embed_provider.py``.
"""
from __future__ import annotations

from typing import Any, cast

import httpx

from agentalloy.lm_client import LMClientError


class OllamaEmbedClient:
    """Embedding client that speaks the Ollama-native ``/api/embed`` protocol.

    Parameters
    ----------
    base_url:
        Ollama server URL (e.g. ``http://localhost:11434``).
    model:
        Embedding model name (e.g. ``qwen3-embedding:0.6b``).
    keep_alive:
        How long Ollama should keep the model loaded after the call
        (passed as ``keep_alive`` query parameter).  Defaults to ``"5m"``.
    timeout:
        Request timeout in seconds.  Defaults to 30.0.

    Notes
    -----
    The ``model`` parameter is passed to the API so callers can override the
    construction-time model — mirroring the OpenAI-compatible client behaviour.

    Raises
    ------
    LMClientError
        If Ollama returns the wrong number of embeddings.
    """

    def __init__(
        self,
        base_url: str,
        *,
        model: str,
        keep_alive: str = "5m",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._keep_alive = keep_alive
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, *, model: str, texts: list[str]) -> list[list[float]]:
        """Batch-embed *texts* using the Ollama-native ``/api/embed`` endpoint.

        The *model* parameter is passed to the API so callers can override the
        construction-time model — mirroring the OpenAI-compatible client behaviour.

        Returns one vector per input text, in the same order.

        Raises
        ------
        LMClientError
            If Ollama returns the wrong number of embeddings.
        """
        if not texts:
            return []

        resp = httpx.post(
            f"{self._base_url}/api/embed",
            json={"model": model, "input": texts, "keep_alive": self._keep_alive},
            timeout=self._timeout,
        )
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        embeddings: list[list[float]] = cast(list[list[float]], data.get("embeddings", []))

        if len(embeddings) != len(texts):
            raise LMClientError(
                f"Ollama returned {len(embeddings)} embeddings for {len(texts)} texts"
            )

        return embeddings

    def close(self) -> None:
        """No-op — this client does not manage a long-lived session."""

    # ------------------------------------------------------------------
    # Context-manager protocol (for uniform usage)
    # ------------------------------------------------------------------

    def __enter__(self) -> OllamaEmbedClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
