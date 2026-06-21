"""Read-only views of what has been harvested."""

from __future__ import annotations

from bhindex.storage.repositories import Repository


class StatsService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def overview(self) -> dict[str, int]:
        return self.repo.stats()

    def by_source(self) -> list[dict]:
        return [dict(row) for row in self.repo.stats_by_source()]

    def events(self) -> list[dict]:
        return [dict(row) for row in self.repo.list_events()]
