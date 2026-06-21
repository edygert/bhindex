"""Single-session retrieval (the `show` command; a future TUI detail screen)."""

from __future__ import annotations

from bhindex.dto.contracts import MaterialDTO, SessionDetailDTO, SpeakerDTO
from bhindex.storage.repositories import Repository


class SessionService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def get(self, session_id: int) -> SessionDetailDTO | None:
        row = self.repo.get_session(session_id)
        if row is None:
            return None
        speakers = [
            SpeakerDTO(name=s["name"], affiliation=s["affiliation"] or None, bio=s["bio"])
            for s in self.repo.get_session_speakers(session_id)
        ]
        materials = [
            MaterialDTO(title=m["title"] or "Material", url=m["url"], kind=m["kind"])
            for m in self.repo.get_session_materials(session_id)
        ]
        return SessionDetailDTO(
            id=row["id"],
            slug=row["slug"],
            event_name=row["event_name"],
            event_slug=row["event_slug"],
            title=row["title"],
            abstract=row["abstract"],
            track=row["track"],
            room=row["room"],
            starts_at=row["starts_at"],
            source_url=row["source_url"],
            speakers=speakers,
            materials=materials,
        )
