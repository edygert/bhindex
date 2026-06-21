"""Service-boundary contracts (pydantic). The only data shapes the CLI/ingest/TUI/API exchange."""

from .contracts import (
    EventDTO,
    HarvestReport,
    IngestPayload,
    MaterialDTO,
    SessionDTO,
    SpeakerDTO,
)

__all__ = [
    "EventDTO",
    "HarvestReport",
    "IngestPayload",
    "MaterialDTO",
    "SessionDTO",
    "SpeakerDTO",
]
