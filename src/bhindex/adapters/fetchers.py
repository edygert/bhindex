"""Fetchers — where HTML comes from. Two only, by design:

* ``WaybackFetcher`` — the primary source. The Wayback Machine is not behind Cloudflare, so it works
  from any network/CI. It enumerates an event's archived pages (CDX) and returns their raw HTML.
* ``FileFetcher`` — manually-saved HTML on disk (the "Save Page As" / offline path). Also how parser
  tests feed fixtures in.

Both yield a ``FetchResult``; the harvester doesn't care which produced it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bhindex.adapters.http_client import HttpClient
from bhindex.core.errors import FetchError
from bhindex.core.models import FetchResult, SourceName
from bhindex.core.urls import is_errors_path, wayback_cdx_url, wayback_raw_url


class Fetcher(Protocol):
    source: SourceName

    def fetch(self, url: str) -> FetchResult: ...


@dataclass(frozen=True, slots=True)
class CdxRow:
    timestamp: str
    original: str
    statuscode: str


class WaybackFetcher:
    source = SourceName.WAYBACK

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def enumerate(
        self,
        url_pattern: str,
        *,
        match_type: str = "prefix",
        from_year: int | None = None,
        to_year: int | None = None,
        collapse: str | None = "urlkey",
    ) -> list[CdxRow]:
        """List archived captures for a pattern (one per URL by default). Skips ``/errors/``."""
        cdx_url = wayback_cdx_url(
            url_pattern, match_type=match_type, from_year=from_year, to_year=to_year,
            collapse=collapse,
        )
        resp = self.client.get(cdx_url)
        rows = json.loads(resp.text) if resp.text.strip() else []
        out: list[CdxRow] = []
        for row in rows[1:]:  # row[0] is the header
            timestamp, original, statuscode = row[0], row[1], row[2]
            if is_errors_path(original):
                continue
            out.append(CdxRow(timestamp=timestamp, original=original, statuscode=statuscode))
        return out

    def latest_capture(self, original_url: str) -> CdxRow | None:
        rows = self.enumerate(original_url, match_type="exact", collapse=None)
        if not rows:
            return None
        return max(rows, key=lambda r: r.timestamp)

    def fetch_capture(self, row: CdxRow) -> FetchResult:
        raw = wayback_raw_url(row.timestamp, row.original)
        resp = self.client.get(raw)
        return FetchResult(
            url=row.original, final_url=raw, status=resp.status,
            html=resp.text, source=self.source,
        )

    def fetch(self, url: str) -> FetchResult:
        """Fetch the latest archived capture of an original URL (ad-hoc single-page use)."""
        row = self.latest_capture(url)
        if row is None:
            raise FetchError("no Wayback capture found", url=url)
        return self.fetch_capture(row)


class FileFetcher:
    """Reads manually-saved HTML. ``base_url`` sets the URL used for resolving relative links."""

    source = SourceName.FILE

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url

    def fetch(self, path: str) -> FetchResult:
        p = Path(path)
        if not p.is_file():
            raise FetchError(f"file not found: {path}", url=path)
        html = p.read_text(encoding="utf-8", errors="replace")
        url = self.base_url or p.as_uri()
        return FetchResult(url=url, final_url=url, status=200, html=html, source=self.source)
