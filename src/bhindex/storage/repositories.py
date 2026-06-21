"""Data-access layer. All SQL lives here; methods take/return DTOs and primitives.

Persistence is aggregate-oriented: ``save_event`` writes an event and its sessions/speakers/materials
atomically. Services own transaction boundaries (call ``commit`` after a batch). Upserts are keyed so
re-harvesting the same URL is idempotent and a later live run merges cleanly over a Wayback run.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from bhindex.dto.contracts import EventDTO, SessionDTO, SpeakerDTO


@dataclass
class SaveCounts:
    events: int = 0
    sessions: int = 0
    speakers: int = 0
    materials: int = 0  # only *new* material links

    def add(self, other: SaveCounts) -> None:
        self.events += other.events
        self.sessions += other.sessions
        self.speakers += other.speakers
        self.materials += other.materials


@dataclass
class Repository:
    conn: sqlite3.Connection
    _source_cache: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------------ sources / snapshots
    def get_or_create_source(self, name: str, detail: str | None = None) -> int:
        if name in self._source_cache:
            return self._source_cache[name]
        self.conn.execute(
            "INSERT INTO sources(name, detail) VALUES(?, ?) ON CONFLICT(name) DO NOTHING",
            (name, detail),
        )
        row = self.conn.execute("SELECT id FROM sources WHERE name = ?", (name,)).fetchone()
        self._source_cache[name] = row[0]
        return row[0]

    def record_snapshot(self, url: str, sha256: str, path: str, http_status: int | None) -> int:
        self.conn.execute(
            "INSERT INTO snapshots(url, sha256, path, http_status) VALUES(?,?,?,?) "
            "ON CONFLICT(sha256) DO NOTHING",
            (url, sha256, path, http_status),
        )
        row = self.conn.execute("SELECT id FROM snapshots WHERE sha256 = ?", (sha256,)).fetchone()
        return row[0]

    # ------------------------------------------------------------------ aggregate save
    def save_event(
        self, event: EventDTO, source_id: int, snapshot_id: int | None = None
    ) -> SaveCounts:
        counts = SaveCounts()
        row = self.conn.execute(
            """
            INSERT INTO events(slug, name, region, year, kind, source_id, source_url, snapshot_id,
                               last_refreshed)
            VALUES(?,?,?,?,?,?,?,?, datetime('now'))
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name, region=excluded.region, year=excluded.year,
                kind=excluded.kind, source_id=excluded.source_id, source_url=excluded.source_url,
                snapshot_id=COALESCE(excluded.snapshot_id, events.snapshot_id),
                last_refreshed=datetime('now')
            RETURNING id
            """,
            (
                event.slug, event.name, event.region, event.year, event.kind.value,
                source_id, event.source_url, snapshot_id,
            ),
        ).fetchone()
        event_id = row[0]
        counts.events += 1
        for session in event.sessions:
            self._save_session(event_id, session, source_id, snapshot_id, counts)
        return counts

    def _save_session(
        self,
        event_id: int,
        s: SessionDTO,
        source_id: int,
        snapshot_id: int | None,
        counts: SaveCounts,
    ) -> int:
        speakers_text = ", ".join(sp.name for sp in s.speakers)
        materials_text = ", ".join(m.title for m in s.materials if m.title)
        row = self.conn.execute(
            """
            INSERT INTO sessions(event_id, slug, title, abstract, track, room, starts_at,
                                 speakers_text, materials_text, source_id, source_url, snapshot_id,
                                 last_refreshed)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
            ON CONFLICT(event_id, slug) DO UPDATE SET
                title=excluded.title, abstract=excluded.abstract, track=excluded.track,
                room=excluded.room, starts_at=excluded.starts_at, speakers_text=excluded.speakers_text,
                materials_text=excluded.materials_text,
                source_id=excluded.source_id, source_url=excluded.source_url,
                snapshot_id=COALESCE(excluded.snapshot_id, sessions.snapshot_id),
                last_refreshed=datetime('now')
            RETURNING id
            """,
            (
                event_id, s.slug, s.title, s.abstract, s.track, s.room, s.starts_at,
                speakers_text, materials_text, source_id, s.source_url, snapshot_id,
            ),
        ).fetchone()
        session_id = row[0]
        counts.sessions += 1

        # Re-linking is a full replace: clear prior speaker links so a re-harvest where a speaker's
        # identity changed (e.g. an affiliation that now decodes differently) doesn't accumulate
        # stale links to obsolete speaker rows.
        self.conn.execute("DELETE FROM session_speakers WHERE session_id = ?", (session_id,))
        for sp in s.speakers:
            speaker_id = self._get_or_create_speaker(sp)
            self.conn.execute(
                "INSERT OR IGNORE INTO session_speakers(session_id, speaker_id) VALUES(?,?)",
                (session_id, speaker_id),
            )
            counts.speakers += 1

        for m in s.materials:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO materials(session_id, title, url, kind) VALUES(?,?,?,?)",
                (session_id, m.title, m.url, m.kind.value),
            )
            if cur.rowcount and cur.rowcount > 0:
                counts.materials += 1
        return session_id

    def _get_or_create_speaker(self, sp: SpeakerDTO) -> int:
        affiliation = sp.affiliation or ""
        self.conn.execute(
            "INSERT INTO speakers(name, affiliation, bio) VALUES(?,?,?) "
            "ON CONFLICT(name, affiliation) DO UPDATE SET bio=COALESCE(excluded.bio, speakers.bio)",
            (sp.name, affiliation, sp.bio),
        )
        row = self.conn.execute(
            "SELECT id FROM speakers WHERE name = ? AND affiliation = ?", (sp.name, affiliation)
        ).fetchone()
        return row[0]

    # ------------------------------------------------------------------ queries
    def search_sessions(self, query: str, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT s.id, s.title, s.track, s.speakers_text, e.name AS event_name,
                   snippet(sessions_fts, 1, '[', ']', '…', 10) AS snippet,
                   bm25(sessions_fts) AS rank
            FROM sessions_fts
            JOIN sessions s ON s.id = sessions_fts.rowid
            JOIN events e ON e.id = s.event_id
            WHERE sessions_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()

    def get_session(self, session_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT s.id, s.slug, s.title, s.abstract, s.track, s.room, s.starts_at, s.source_url,
                   e.slug AS event_slug, e.name AS event_name
            FROM sessions s JOIN events e ON e.id = s.event_id
            WHERE s.id = ?
            """,
            (session_id,),
        ).fetchone()

    def get_session_speakers(self, session_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT sp.name, sp.affiliation, sp.bio
            FROM speakers sp JOIN session_speakers ss ON ss.speaker_id = sp.id
            WHERE ss.session_id = ? ORDER BY sp.name
            """,
            (session_id,),
        ).fetchall()

    def get_session_materials(self, session_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT title, url, kind FROM materials WHERE session_id = ? ORDER BY kind, title",
            (session_id,),
        ).fetchall()

    def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for table in ("events", "sessions", "speakers", "materials", "snapshots"):
            out[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return out

    def stats_by_source(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT COALESCE(src.name, '?') AS source,
                   COUNT(DISTINCT e.id) AS events,
                   COUNT(DISTINCT s.id) AS sessions
            FROM sessions s
            JOIN events e ON e.id = s.event_id
            LEFT JOIN sources src ON src.id = s.source_id
            GROUP BY src.name
            ORDER BY sessions DESC
            """
        ).fetchall()

    def list_events(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT e.slug, e.name, e.year, e.kind,
                   (SELECT COUNT(*) FROM sessions s WHERE s.event_id = e.id) AS sessions
            FROM events e ORDER BY e.year DESC, e.name
            """
        ).fetchall()

    # ------------------------------------------------------------------ harvest runs
    def start_run(self, source_id: int) -> int:
        cur = self.conn.execute("INSERT INTO harvest_runs(source_id) VALUES(?)", (source_id,))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(
        self, run_id: int, counts: SaveCounts, urls_seen: int, errors: int, status: str
    ) -> None:
        self.conn.execute(
            """
            UPDATE harvest_runs SET finished_at=datetime('now'), urls_seen=?, events_upserted=?,
                   sessions_upserted=?, materials_upserted=?, errors=?, status=?
            WHERE id=?
            """,
            (urls_seen, counts.events, counts.sessions, counts.materials, errors, status, run_id),
        )
        self.conn.commit()

    def prune_orphan_speakers(self) -> int:
        """Delete speaker rows no longer linked to any session.

        Re-harvesting where a speaker's identity changed (e.g. an affiliation/name that now decodes
        differently) re-links the session to the new row and leaves the old one orphaned. Returns the
        number pruned. Safe: a speaker shared across events is only removed when no session links it.
        """
        cur = self.conn.execute(
            "DELETE FROM speakers WHERE id NOT IN (SELECT speaker_id FROM session_speakers)"
        )
        return cur.rowcount or 0

    def commit(self) -> None:
        self.conn.commit()
