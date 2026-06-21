-- bhindex schema. Idempotent (IF NOT EXISTS). FTS5 over sessions via external-content + triggers.

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,          -- SourceName enum value: wayback / live-http / ingest / file ...
    detail TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY,
    url         TEXT NOT NULL,
    sha256      TEXT NOT NULL UNIQUE,      -- dedupe identical captures
    path        TEXT NOT NULL,             -- on-disk raw HTML (relative to snapshot_dir)
    http_status INTEGER,
    fetched_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY,
    slug           TEXT NOT NULL UNIQUE,   -- canonical edition slug, e.g. "us-2024"
    name           TEXT NOT NULL,
    region         TEXT,
    year           INTEGER,
    kind           TEXT NOT NULL,          -- recent | legacy
    source_id      INTEGER REFERENCES sources(id),
    source_url     TEXT,
    snapshot_id    INTEGER REFERENCES snapshots(id),
    first_seen     TEXT NOT NULL DEFAULT (datetime('now')),
    last_refreshed TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY,
    event_id       INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    slug           TEXT NOT NULL,          -- stable within event (anchor id or slugified title)
    title          TEXT NOT NULL,
    abstract       TEXT,
    track          TEXT,
    room           TEXT,
    starts_at      TEXT,
    speakers_text  TEXT NOT NULL DEFAULT '',  -- denormalized speaker names, for FTS
    source_id      INTEGER REFERENCES sources(id),
    source_url     TEXT,
    snapshot_id    INTEGER REFERENCES snapshots(id),
    last_refreshed TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (event_id, slug)
);

CREATE TABLE IF NOT EXISTS speakers (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    affiliation TEXT,
    bio         TEXT,
    UNIQUE (name, affiliation)
);

CREATE TABLE IF NOT EXISTS session_speakers (
    session_id INTEGER NOT NULL REFERENCES sessions(id)  ON DELETE CASCADE,
    speaker_id INTEGER NOT NULL REFERENCES speakers(id)  ON DELETE CASCADE,
    PRIMARY KEY (session_id, speaker_id)
);

-- Material *links* only. Presence here never implies a downloaded binary (Phase 1 invariant).
CREATE TABLE IF NOT EXISTS materials (
    id            INTEGER PRIMARY KEY,
    session_id    INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    title         TEXT,
    url           TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'other',
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, url)
);

CREATE TABLE IF NOT EXISTS harvest_runs (
    id                INTEGER PRIMARY KEY,
    source_id         INTEGER REFERENCES sources(id),
    started_at        TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at       TEXT,
    urls_seen         INTEGER DEFAULT 0,
    events_upserted   INTEGER DEFAULT 0,
    sessions_upserted INTEGER DEFAULT 0,
    materials_upserted INTEGER DEFAULT 0,
    errors            INTEGER DEFAULT 0,
    status            TEXT DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS idx_sessions_event ON sessions(event_id);
CREATE INDEX IF NOT EXISTS idx_materials_session ON materials(session_id);

-- Full-text search over sessions. External-content table mirrors the sessions table; the triggers
-- below keep it in sync. speakers_text is denormalized into sessions so a single trigger set covers it.
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    title, abstract, track, speakers_text,
    content='sessions', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, title, abstract, track, speakers_text)
    VALUES (new.id, new.title, new.abstract, new.track, new.speakers_text);
END;

CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, title, abstract, track, speakers_text)
    VALUES ('delete', old.id, old.title, old.abstract, old.track, old.speakers_text);
END;

CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, title, abstract, track, speakers_text)
    VALUES ('delete', old.id, old.title, old.abstract, old.track, old.speakers_text);
    INSERT INTO sessions_fts(rowid, title, abstract, track, speakers_text)
    VALUES (new.id, new.title, new.abstract, new.track, new.speakers_text);
END;
