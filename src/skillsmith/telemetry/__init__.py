"""Telemetry writer — persists composition and retrieval traces.

Per v5.3, traces land in DuckDB ``composition_traces`` (same
``skills.duck`` file as fragment_embeddings). Writes are inline before
response; failures log but never propagate.
"""

from __future__ import annotations

from skillsmith.telemetry.writer import (
    DuckDBTelemetryWriter,
    NullTelemetryWriter,
    TelemetryRecord,
    TelemetryWriter,
)

__all__ = [
    "DuckDBTelemetryWriter",
    "NullTelemetryWriter",
    "TelemetryRecord",
    "TelemetryWriter",
]
