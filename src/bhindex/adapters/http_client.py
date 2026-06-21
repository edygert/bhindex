"""A small, polite HTTP getter — the only thing that touches the network.

Deliberately minimal: bhindex harvests from the Wayback Machine once per event, so there is no
concurrency. It paces requests (fixed delay + jitter), and on transient failures / rate-limiting
(429, 5xx) it backs off exponentially while honoring ``Retry-After``. A ``notify`` hook lets the CLI
surface "being throttled, waiting Ns" live.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from bhindex.core.config import Settings
from bhindex.core.errors import FetchError
from bhindex.core.logging import get_logger

Notify = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    text: str
    final_url: str


class HttpClient:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        *,
        notify: Notify | None = None,
    ) -> None:
        self.settings = settings
        self.notify = notify
        self.log = get_logger()
        self._last_request = 0.0
        self._client = client or httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.timeout,
            follow_redirects=True,
        )

    def _wait_turn(self) -> None:
        target = self.settings.request_delay + random.uniform(0, 1.0)  # jitter
        elapsed = time.monotonic() - self._last_request
        if elapsed < target:
            time.sleep(target - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str) -> HttpResponse:
        attempts = self.settings.max_retries + 1
        for attempt in range(1, attempts + 1):
            self._wait_turn()
            try:
                resp = self._client.get(url)
            except httpx.HTTPError as exc:
                if attempt == attempts:
                    raise FetchError(f"network error: {exc}", url=url) from exc
                self._backoff(attempt, url, "network error", None)
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts:
                self._backoff(attempt, url, f"status {resp.status_code}", resp)
                continue
            if resp.status_code >= 400:
                raise FetchError(f"HTTP {resp.status_code}", url=url, status=resp.status_code)
            return HttpResponse(resp.status_code, resp.text, str(resp.url))
        raise FetchError("exhausted retries", url=url)  # pragma: no cover

    def _backoff(self, attempt: int, url: str, why: str, resp: httpx.Response | None) -> None:
        retry_after: float | None = None
        if resp is not None and "retry-after" in resp.headers:
            try:
                retry_after = float(resp.headers["retry-after"])
            except ValueError:
                retry_after = None
        base = self.settings.request_delay
        wait = retry_after if retry_after is not None else base * (2 ** (attempt - 1))
        wait = max(wait, base) + random.uniform(0, 1.0)
        msg = f"{why}: backing off {wait:.0f}s (retry {attempt}/{self.settings.max_retries})"
        self.log.warning("http: %s on %s", msg, url)
        if self.notify:
            self.notify(msg)
        time.sleep(wait)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
