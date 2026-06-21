"""Pydantic contracts exchanged across the service boundary.

Parsers produce these; services consume/return them; storage maps them to rows. They are also
valid FastAPI request/response models, so the deferred web layer wraps the same services unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from bhindex.core.models import EventKind, MaterialKind, SourceName


class SpeakerDTO(BaseModel):
    name: str
    affiliation: str | None = None
    bio: str | None = None


class MaterialDTO(BaseModel):
    """A *link* to downloadable material. Phase 1 stores the URL only; nothing is downloaded."""

    title: str
    url: str
    kind: MaterialKind = MaterialKind.OTHER


class SessionDTO(BaseModel):
    slug: str  # stable within an event (anchor id, or slugified title)
    title: str
    abstract: str | None = None
    track: str | None = None
    room: str | None = None
    starts_at: str | None = None  # raw text as published; normalization is out of scope for Phase 1
    source_url: str
    speakers: list[SpeakerDTO] = Field(default_factory=list)
    materials: list[MaterialDTO] = Field(default_factory=list)


class SessionDetailDTO(BaseModel):
    """A fully-resolved session for display (the `show` command / future detail screen)."""

    id: int
    slug: str
    event_name: str
    event_slug: str
    title: str
    abstract: str | None = None
    track: str | None = None
    room: str | None = None
    starts_at: str | None = None
    source_url: str
    speakers: list[SpeakerDTO] = Field(default_factory=list)
    materials: list[MaterialDTO] = Field(default_factory=list)


class EventDTO(BaseModel):
    slug: str  # canonical edition slug, e.g. "us-2024"
    name: str  # display, e.g. "USA 2024"
    region: str | None = None
    year: int | None = None
    kind: EventKind = EventKind.RECENT
    source_url: str
    sessions: list[SessionDTO] = Field(default_factory=list)


class IngestPayload(BaseModel):
    """Body accepted by the local ingest endpoint (browser extension/bookmarklet).

    Either raw ``html`` (re-parsed server-side) or already-extracted ``events``.
    """

    url: str
    html: str | None = None
    events: list[EventDTO] = Field(default_factory=list)


class HarvestReport(BaseModel):
    source: SourceName
    edition: str | None = None
    urls_seen: int = 0
    events_upserted: int = 0
    sessions_upserted: int = 0
    speakers_upserted: int = 0
    materials_upserted: int = 0

    # Diagnostics — validate that the feed matched the expected shape and flag missing data.
    materials_from_feed: int = 0
    materials_backfilled: int = 0
    backfill_unmatched: int = 0
    sessions_without_abstract: int = 0
    sessions_without_speakers: int = 0
    sessions_without_materials: int = 0
    dangling_speaker_refs: int = 0
    anomalies: list[str] = Field(default_factory=list)

    errors: list[str] = Field(default_factory=list)
    status: str = "ok"

    def merge(self, other: HarvestReport) -> None:
        self.urls_seen += other.urls_seen
        self.events_upserted += other.events_upserted
        self.sessions_upserted += other.sessions_upserted
        self.speakers_upserted += other.speakers_upserted
        self.materials_upserted += other.materials_upserted
        self.errors.extend(other.errors)
