"""Raw-HTML snapshot store: content-addressed files on disk + a row via the Repository.

Snapshots make harvests debuggable and provide ready-made parser-test fixtures (the same bytes the
parser saw). Files are named by sha256, so identical captures are stored once.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .repositories import Repository


class SnapshotStore:
    def __init__(self, repo: Repository, snapshot_dir: Path) -> None:
        self.repo = repo
        self.snapshot_dir = Path(snapshot_dir)

    def save(self, url: str, html: str, http_status: int | None) -> int:
        sha = hashlib.sha256(html.encode("utf-8", "replace")).hexdigest()
        rel = f"{sha[:2]}/{sha}.html"
        path = self.snapshot_dir / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
        return self.repo.record_snapshot(url, sha, rel, http_status)
