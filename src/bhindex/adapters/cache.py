"""On-disk cache of fetched Wayback responses, keyed by URL.

The Wayback captures bhindex pulls (the sessions.json feeds and the /docs CDX enumerations) are
immutable, so there's no reason to re-download them every harvest. This stores each successful
response as one JSON file per URL; ``HttpClient`` consults it before hitting the network.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CachedResponse:
    url: str
    status: int
    body: str


class FetchCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)

    def _path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json"

    def get(self, url: str) -> CachedResponse | None:
        path = self._path(url)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return CachedResponse(url=url, status=data["status"], body=data["body"])

    def put(self, url: str, status: int, body: str) -> None:
        path = self._path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "url": url,
            "status": status,
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "body": body,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)  # atomic
