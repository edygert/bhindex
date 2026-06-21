"""Full-text search over sessions."""

from __future__ import annotations

import re

from bhindex.storage.repositories import Repository

_TERM = re.compile(r"[A-Za-z0-9]+")
_MIN_TERM = 3  # the trigram tokenizer can't match terms shorter than 3 characters


def _safe_fts_query(query: str) -> str:
    """Build an FTS5 query from free text for the **trigram**-tokenized index.

    Each alphanumeric term >= 3 chars becomes a quoted substring match (quoting keeps arbitrary user
    input from tripping FTS5 syntax); terms are AND-ed. With the trigram tokenizer a quoted term
    matches anywhere inside a word, so ``hyper`` finds ``hypervisor``. Terms shorter than 3 chars are
    dropped (they can't be matched); an empty result -> matches nothing.
    """
    terms = [t for t in _TERM.findall(query) if len(t) >= _MIN_TERM]
    return " AND ".join(f'"{t}"' for t in terms)


class SearchService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def _plan(self, query: str) -> tuple[str, object] | None:
        """Decide how to run a query. The trigram index can't match terms < 3 chars, so a query with
        any short term (e.g. "ai", "os", "5g") uses a LIKE scan; otherwise the fast, ranked FTS path.
        """
        terms = _TERM.findall(query)
        if not terms:
            return None
        if any(len(t) < _MIN_TERM for t in terms):
            return ("like", terms)
        return ("fts", _safe_fts_query(query))

    def search(self, query: str, limit: int | None = 50) -> list[dict]:
        """Return up to ``limit`` matching sessions (``limit=None`` returns all)."""
        plan = self._plan(query)
        if plan is None:
            return []
        kind, arg = plan
        rows = (
            self.repo.search_sessions_like(arg, limit) if kind == "like"
            else self.repo.search_sessions(arg, limit)
        )
        return [dict(row) for row in rows]

    def count(self, query: str) -> int:
        """Total number of sessions matching ``query`` (ignores any display limit)."""
        plan = self._plan(query)
        if plan is None:
            return 0
        kind, arg = plan
        return self.repo.count_sessions_like(arg) if kind == "like" else self.repo.count_sessions(arg)
