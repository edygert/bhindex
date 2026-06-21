"""HarvestService — orchestrates fetch -> parse -> validate -> backfill -> persist, one event at a time.

Scope: recent events (2016+) via the sessions.json feed, harvested from the Wayback Machine. For
2016/2017 (whose feed carries no materials) it backfills material links from the archived
``blackhat.com/docs/<ev>/`` tree. Runs sequentially — no concurrency by design.

``harvest_many`` shares a single paced HTTP client across all editions so request spacing is
continuous (more polite than re-pacing per edition), and forwards a ``progress`` callback so the CLI
can show live status — including when the Wayback Machine throttles us.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from bhindex.adapters.fetchers import FileFetcher, WaybackFetcher
from bhindex.adapters.http_client import HttpClient
from bhindex.core.config import Settings
from bhindex.core.errors import BhIndexError, FetchError
from bhindex.core.logging import get_logger
from bhindex.core.models import FetchResult
from bhindex.core.urls import edition_token
from bhindex.dto.contracts import HarvestReport
from bhindex.parsers import recent, registry
from bhindex.parsers.materials import attach_doc_materials, looks_like_material
from bhindex.storage.repositories import Repository
from bhindex.storage.snapshots import SnapshotStore

Progress = Callable[[str], None]


class HarvestService:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        snapshots: SnapshotStore,
        *,
        wayback: WaybackFetcher | None = None,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.snapshots = snapshots
        self._wayback = wayback  # injectable for tests
        self.log = get_logger()

    @contextmanager
    def _fetcher(self, notify: Progress | None = None) -> Iterator[WaybackFetcher]:
        if self._wayback is not None:
            yield self._wayback
            return
        with HttpClient(self.settings, notify=notify) as client:
            yield WaybackFetcher(client)

    # ------------------------------------------------------------------ public API
    def harvest_recent(
        self, edition: str, *, backfill_materials: bool = True, progress: Progress | None = None
    ) -> HarvestReport:
        """Harvest one edition (e.g. ``us-24``) from its Wayback-archived sessions.json feed."""
        with self._fetcher(notify=progress) as wb:
            return self._harvest_one(wb, edition, backfill_materials, progress)

    def harvest_many(
        self,
        editions: list[str],
        *,
        backfill_materials: bool = True,
        on_event: Callable[[str, HarvestReport], None] | None = None,
        progress: Progress | None = None,
    ) -> list[HarvestReport]:
        """Harvest several editions over one shared, continuously-paced client."""
        reports: list[HarvestReport] = []
        with self._fetcher(notify=progress) as wb:
            for edition in editions:
                report = self._harvest_one(wb, edition, backfill_materials, progress)
                reports.append(report)
                if on_event is not None:
                    on_event(edition, report)
        return reports

    def ingest_file(self, path: str, *, base_url: str | None = None) -> HarvestReport:
        """Parse a manually-saved page (e.g. a saved sessions.json) and persist it."""
        result = FileFetcher(base_url=base_url).fetch(path)
        event = registry.parse_event_page(result)
        return self._persist(result, event)

    # ------------------------------------------------------------------ core flow
    def _harvest_one(
        self, wb: WaybackFetcher, edition: str, backfill_materials: bool, progress: Progress | None
    ) -> HarvestReport:
        say = progress or (lambda _msg: None)
        token = edition_token(edition)
        if token is None:
            raise BhIndexError(f"unrecognized edition {edition!r} (expected e.g. 'us-24', 'eu-23')")
        feed_url = recent.feed_url_for_schedule(
            f"https://www.blackhat.com/{token}/briefings/schedule/"
        )

        say(f"{token}: fetching sessions.json")
        try:
            result = wb.fetch(feed_url)
        except FetchError as exc:
            self.log.error("harvest %s: %s", token, exc)
            return HarvestReport(
                source=WaybackFetcher.source, edition=token, status="error",
                anomalies=["no Wayback capture of sessions.json"], errors=[str(exc)],
            )

        try:
            data = json.loads(result.html)
        except json.JSONDecodeError as exc:
            return HarvestReport(
                source=WaybackFetcher.source, edition=token, status="error",
                anomalies=["feed is not valid JSON"], errors=[str(exc)],
            )

        anomalies = self._validate_feed_shape(data)
        event = recent.parse_feed(data, source_url=feed_url)
        say(f"{token}: parsed {len(event.sessions)} sessions")
        materials_from_feed = sum(len(s.materials) for s in event.sessions)

        attached = unmatched = 0
        if backfill_materials:
            say(f"{token}: scanning /docs for materials")
            attached, unmatched = self._backfill(wb, token, event)

        say(f"{token}: saving")
        report = self._persist(result, event)
        self._add_diagnostics(
            report, token, data, event, anomalies, materials_from_feed, attached, unmatched
        )
        self.log.info(
            "harvested %s: %d sessions, %d speakers, %d materials (%d anomalies)",
            token, report.sessions_upserted, report.speakers_upserted,
            report.materials_upserted, len(report.anomalies),
        )
        return report

    # ------------------------------------------------------------------ validation / diagnostics
    @staticmethod
    def _validate_feed_shape(data) -> list[str]:
        """Check the feed matches the expected sessions.json shape; return anomaly strings."""
        anomalies: list[str] = []
        if not isinstance(data, dict):
            return ["feed top-level is not a JSON object"]
        if "sessions" not in data:
            anomalies.append("feed missing 'sessions' key")
        elif not isinstance(data["sessions"], (dict, list)):
            anomalies.append("'sessions' is neither object nor array")
        if "speakers" not in data:
            anomalies.append("feed missing 'speakers' key")
        elif not isinstance(data["speakers"], (dict, list)):
            anomalies.append("'speakers' is neither object nor array")
        return anomalies

    def _add_diagnostics(
        self, report, token, data, event, anomalies, materials_from_feed, attached, unmatched
    ) -> None:
        report.edition = token
        report.materials_from_feed = materials_from_feed
        report.materials_backfilled = attached
        report.backfill_unmatched = unmatched
        report.sessions_without_abstract = sum(1 for s in event.sessions if not s.abstract)
        report.sessions_without_speakers = sum(1 for s in event.sessions if not s.speakers)
        report.sessions_without_materials = sum(1 for s in event.sessions if not s.materials)
        report.dangling_speaker_refs = self._count_dangling_refs(data)

        n = len(event.sessions)
        if n == 0:
            anomalies.append("0 sessions parsed from feed")
        if materials_from_feed == 0 and attached == 0:
            anomalies.append("no materials found (feed has none and /docs backfill empty)")
        if n and report.sessions_without_abstract == n:
            anomalies.append("every session is missing an abstract")
        if report.dangling_speaker_refs:
            anomalies.append(f"{report.dangling_speaker_refs} speaker refs not found in 'speakers'")
        report.anomalies = anomalies

    @staticmethod
    def _count_dangling_refs(data) -> int:
        if not isinstance(data, dict):
            return 0
        speakers = data.get("speakers")
        index = set(speakers) if isinstance(speakers, dict) else {
            str(s.get("person_id")) for s in (speakers or []) if isinstance(s, dict)
        }
        sessions = data.get("sessions") or {}
        values = sessions.values() if isinstance(sessions, dict) else sessions
        dangling = 0
        for s in values:
            if not isinstance(s, dict):
                continue
            for ref in recent.coerce(s.get("speakers")) or []:
                if isinstance(ref, dict) and str(ref.get("person_id")) not in index:
                    dangling += 1
        return dangling

    # ------------------------------------------------------------------ internals
    def _backfill(self, wb: WaybackFetcher, token: str, event) -> tuple[int, int]:
        urls = self._enumerate_doc_materials(wb, token)
        if not urls:
            return 0, 0
        attached, unmatched = attach_doc_materials(event, urls)
        self.log.info(
            "%s materials backfill: %d attached, %d unmatched of %d /docs files",
            token, attached, len(unmatched), len(urls),
        )
        return attached, len(unmatched)

    def _enumerate_doc_materials(self, wb: WaybackFetcher, token: str) -> list[str]:
        try:
            rows = wb.enumerate(
                f"blackhat.com/docs/{token}/", match_type="prefix", collapse="urlkey"
            )
        except FetchError as exc:
            self.log.warning("%s /docs enumerate failed: %s", token, exc)
            return []
        urls: set[str] = set()
        for r in rows:
            url = r.original.split("?", 1)[0]
            if looks_like_material(url):
                urls.add(url)
        return sorted(urls)

    def _persist(self, result: FetchResult, event) -> HarvestReport:
        source_id = self.repo.get_or_create_source(result.source.value)
        snapshot_id = self.snapshots.save(result.url, result.html, result.status)
        counts = self.repo.save_event(event, source_id, snapshot_id)
        self.repo.prune_orphan_speakers()  # drop speaker rows orphaned by re-harvest identity changes
        self.repo.commit()
        return HarvestReport(
            source=result.source,
            urls_seen=1,
            events_upserted=counts.events,
            sessions_upserted=counts.sessions,
            speakers_upserted=counts.speakers,
            materials_upserted=counts.materials,
        )
