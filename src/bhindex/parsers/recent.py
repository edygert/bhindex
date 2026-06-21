"""Recent-event parser: the ``briefings/schedule/sessions.json`` feed.

Modern Black Hat schedule pages are Handlebars templates rendered client-side from this JSON feed.
Parsing the feed is far more reliable than scraping the rendered DOM. Shape:

    { "sessions": { "<id>": {title, description, track_1/2, room, time_*, speakers, bh_files, ...} },
      "speakers": { "<person_id>": {first_name, last_name, company, title, bio, ...} } }

Some scalar fields arrive as JSON strings holding Python-repr lists/dicts (e.g. speakers), so we
coerce defensively.
"""

from __future__ import annotations

import ast
import json
from typing import Any

from bhindex.core.models import EventKind
from bhindex.core.urls import parse_edition
from bhindex.dto.contracts import EventDTO, MaterialDTO, SessionDTO, SpeakerDTO

from .base import clean, strip_html
from .materials import classify

SESSIONS_JSON_SUFFIX = "sessions.json"


def feed_url_for_schedule(schedule_url: str) -> str:
    base = schedule_url if schedule_url.endswith("/") else schedule_url.rsplit("/", 1)[0] + "/"
    return base + SESSIONS_JSON_SUFFIX


def coerce(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s or s == "None":
        return None
    try:
        return json.loads(s)
    except Exception:
        try:
            return ast.literal_eval(s)
        except Exception:
            return None


def _track(session: dict[str, Any]) -> str | None:
    parts = [clean(session.get("track_1")), clean(session.get("track_2"))]
    joined = ", ".join(p for p in parts if p)
    return joined or None


def _speakers(session: dict[str, Any], index: dict[str, dict]) -> list[SpeakerDTO]:
    out: list[SpeakerDTO] = []
    for ref in coerce(session.get("speakers")) or []:
        if not isinstance(ref, dict):
            continue
        person = index.get(str(ref.get("person_id")))
        if not person:
            continue
        name = clean(" ".join(p for p in (person.get("first_name"), person.get("last_name")) if p))
        if not name:
            continue
        out.append(
            SpeakerDTO(
                name=name,
                affiliation=clean(person.get("company")),
                bio=strip_html(person.get("bio")),
            )
        )
    return out


def _materials(session: dict[str, Any]) -> list[MaterialDTO]:
    out: list[MaterialDTO] = []
    files = coerce(session.get("bh_files")) or {}
    if isinstance(files, dict):
        for category, entry in files.items():
            if not isinstance(entry, dict):
                continue
            url = clean(entry.get("url"))
            if not url:
                continue
            label = clean(entry.get("label")) or category.replace("_", " ").title()
            out.append(MaterialDTO(title=label, url=url, kind=classify(url, hint=label or category)))
    # Recording / embedded video, when published as a URL.
    recording = clean(session.get("recording"))
    if recording and recording.lower().startswith("http"):
        out.append(MaterialDTO(title="Recording", url=recording, kind=classify(recording, hint="video")))
    for vid in coerce(session.get("embedVideo")) or []:
        url = vid.get("url") if isinstance(vid, dict) else vid
        if isinstance(url, str) and url.startswith("http"):
            out.append(MaterialDTO(title="Video", url=url, kind=classify(url, hint="video")))
    return out


def parse_feed(feed: str | dict, *, source_url: str) -> EventDTO:
    data = json.loads(feed) if isinstance(feed, str) else feed
    sessions = data.get("sessions") or {}
    speakers_raw = data.get("speakers") or {}
    index: dict[str, dict] = (
        speakers_raw if isinstance(speakers_raw, dict)
        else {str(s.get("person_id")): s for s in speakers_raw}
    )

    edition = parse_edition(source_url)
    base = source_url.rsplit("sessions.json", 1)[0]

    session_items = sessions.values() if isinstance(sessions, dict) else sessions
    dtos: list[SessionDTO] = []
    for s in session_items:
        if not s:
            continue
        title = clean(s.get("title"))
        if not title:
            continue
        slug = str(s.get("id") or title)
        abstract = strip_html(s.get("description")) or strip_html(s.get("marketing_description"))
        dtos.append(
            SessionDTO(
                slug=slug,
                title=title,
                abstract=abstract,
                track=_track(s),
                room=clean(s.get("room")),
                starts_at=clean(s.get("time_display")) or clean(s.get("iso_start_date")),
                source_url=f"{base}#{slug}",
                speakers=_speakers(s, index),
                materials=_materials(s),
            )
        )

    slug = edition.slug if edition else "unknown"
    name = edition.name if edition else "Black Hat (unknown edition)"
    return EventDTO(
        slug=slug,
        name=name,
        region=edition.region if edition else None,
        year=edition.year if edition else None,
        kind=EventKind.RECENT,
        source_url=source_url,
        sessions=dtos,
    )
