"""SQLite connection factory + FTS5 capability probe."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bhindex.core.errors import StorageError


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a connection with sane pragmas. ``:memory:`` is supported for tests."""
    is_memory = str(db_path) == ":memory:"
    if not is_memory:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not is_memory:
        conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def fts5_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def require_fts5(conn: sqlite3.Connection) -> None:
    if not fts5_available(conn):
        raise StorageError(
            "This Python's bundled SQLite was built without FTS5; full-text search is unavailable."
        )
