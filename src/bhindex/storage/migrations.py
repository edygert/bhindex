"""Schema application + versioning. The schema is idempotent, so apply() is safe to re-run."""

from __future__ import annotations

import sqlite3
from importlib import resources

from .db import require_fts5

SCHEMA_VERSION = 2  # v2: sessions.materials_text added to sessions_fts (material titles searchable)


def _load_schema_sql() -> str:
    return resources.files("bhindex.storage").joinpath("schema.sql").read_text(encoding="utf-8")


def apply(conn: sqlite3.Connection) -> int:
    """Create/upgrade the schema. Returns the resulting schema version."""
    require_fts5(conn)
    conn.executescript(_load_schema_sql())
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    elif row[0] < SCHEMA_VERSION:
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    conn.commit()
    return SCHEMA_VERSION


def current_version(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None
