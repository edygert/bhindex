"""Integration: HarvestService -> storage, driven by a fake fetcher (no network).

Also pins the Phase-1 invariant: harvesting writes only metadata + HTML snapshots, never binaries.
"""

from __future__ import annotations

from bhindex.adapters.fetchers import CdxRow
from bhindex.core.models import FetchResult, SourceName
from bhindex.services import ServiceContainer


class FakeWayback:
    """Serves the fixture feed for any sessions.json fetch; configurable /docs enumeration."""

    source = SourceName.WAYBACK

    def __init__(self, feed_html: str, doc_urls: list[str] | None = None) -> None:
        self.feed_html = feed_html
        self.doc_urls = doc_urls or []

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(url=url, final_url=url, status=200, html=self.feed_html, source=self.source)

    def enumerate(self, pattern, **kwargs) -> list[CdxRow]:
        return [CdxRow(timestamp="20240101", original=u, statuscode="200") for u in self.doc_urls]


def _app(settings, feed_html, doc_urls=None) -> ServiceContainer:
    app = ServiceContainer(settings)
    app.harvest._wayback = FakeWayback(feed_html, doc_urls)
    return app


def test_harvest_persists_sessions_and_fts(temp_settings, feed_json):
    app = _app(temp_settings, feed_json)
    report = app.harvest.harvest_recent("us-24")
    try:
        assert report.status == "ok"
        assert report.sessions_upserted == 3
        assert app.stats.overview()["sessions"] == 3
        assert app.stats.by_source()[0]["source"] == "wayback"
        assert app.search.search("timing")  # FTS works end-to-end
    finally:
        app.close()


def test_backfill_attaches_doc_materials(temp_settings, feed_json):
    # A /docs file whose filename matches a fixture speaker (Kettle) should attach.
    doc = "https://www.blackhat.com/docs/us-24/us-24-Kettle-Extra-Notes.pdf"
    app = _app(temp_settings, feed_json, doc_urls=[doc])
    app.harvest.harvest_recent("us-24")
    try:
        rows = app.search.search("Whispers")
        assert rows  # session present
        mats = app.repo.conn.execute(
            "SELECT url FROM materials WHERE url = ?", (doc,)
        ).fetchall()
        assert mats, "backfilled /docs material should be stored"
    finally:
        app.close()


def test_harvest_writes_no_binary_files(temp_settings, feed_json):
    app = _app(temp_settings, feed_json)
    app.harvest.harvest_recent("us-24")
    app.close()
    exts = {p.suffix.lower() for p in temp_settings.data_dir.rglob("*") if p.is_file()}
    assert exts.isdisjoint({".pdf", ".m4v", ".mp4", ".zip", ".mp3", ".pptx"})


def test_unknown_edition_reports_error(temp_settings, feed_json):
    app = _app(temp_settings, feed_json)
    try:
        import pytest

        from bhindex.core.errors import BhIndexError
        with pytest.raises(BhIndexError):
            app.harvest.harvest_recent("not-an-edition")
    finally:
        app.close()
