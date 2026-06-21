"""Route a fetched page to the right parser. Scope is recent events (the sessions.json feed)."""

from __future__ import annotations

from bhindex.core.models import FetchResult
from bhindex.dto.contracts import EventDTO

from . import recent


def looks_like_feed(result: FetchResult) -> bool:
    if result.url.endswith(recent.SESSIONS_JSON_SUFFIX):
        return True
    head = result.html.lstrip()[:1]
    return head in ("{", "[")


def parse_event_page(result: FetchResult) -> EventDTO:
    """Parse a fetched page into an event. Only the sessions.json feed carries data.

    A recent schedule *HTML* page is a Handlebars template with no data, so it yields an empty event —
    the caller should fetch the sessions.json feed instead.
    """
    if looks_like_feed(result):
        return recent.parse_feed(result.html, source_url=result.url)
    return recent.parse_feed({"sessions": {}, "speakers": {}}, source_url=result.url)
