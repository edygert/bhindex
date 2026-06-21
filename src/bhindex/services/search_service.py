"""Full-text search over sessions."""

from __future__ import annotations

import re

from bhindex.storage.repositories import Repository

_TERM = re.compile(r"[A-Za-z0-9]+")


def _safe_fts_query(query: str) -> str:
    """Quote each term so arbitrary user input can't trip FTS5 syntax. Empty -> matches nothing."""
    terms = _TERM.findall(query)
    return " ".join(f'"{t}"' for t in terms)


class SearchService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def search(self, query: str, limit: int = 50) -> list[dict]:
        fts = _safe_fts_query(query)
        if not fts:
            return []
        return [dict(row) for row in self.repo.search_sessions(fts, limit)]
