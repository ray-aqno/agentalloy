"""Retrieval pipeline — embed, filter, rank, diversify."""

from __future__ import annotations

from skillsmith.retrieval.domain import (
    RetrievalResult,
    phase_to_categories,
    retrieve_domain_candidates,
)
from skillsmith.retrieval.similarity import cosine_similarity
from skillsmith.retrieval.system import SystemRetrievalResult, retrieve_system_fragments

__all__ = [
    "RetrievalResult",
    "SystemRetrievalResult",
    "cosine_similarity",
    "phase_to_categories",
    "retrieve_domain_candidates",
    "retrieve_system_fragments",
]
