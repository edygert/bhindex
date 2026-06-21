"""Small value types + enums shared across layers.

Richer data carriers (Event/Session/Speaker/Material) live in ``bhindex.dto.contracts`` as pydantic
models — they double as the service-boundary contract and (later) FastAPI response models.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventKind(StrEnum):
    # Scope is 2016+ recent events only (sessions.json feed); legacy archives are out of scope.
    RECENT = "recent"


class SourceName(StrEnum):
    WAYBACK = "wayback"  # primary: Wayback Machine (no Cloudflare)
    FILE = "file"  # manually-saved HTML on disk


class MaterialKind(StrEnum):
    PDF = "pdf"
    SLIDES = "slides"
    WHITEPAPER = "whitepaper"
    VIDEO = "video"
    AUDIO = "audio"
    TOOL = "tool"
    ARCHIVE = "archive"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Outcome of a single fetch, regardless of which Fetcher produced it."""

    url: str  # the URL we asked for
    final_url: str  # after redirects (the original target for Wayback raw fetches)
    status: int
    html: str
    source: SourceName
    from_cache: bool = False
