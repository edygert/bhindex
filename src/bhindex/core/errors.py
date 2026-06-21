"""Exception hierarchy for bhindex.

Errors are deliberately granular so the harvester can decide retry/abort policy and so the
(future) TUI/API can surface actionable messages. ``CloudflareChallenge`` and ``RobotsDisallowed``
are *terminal* for a given URL — they must never trigger a retry storm.
"""

from __future__ import annotations


class BhIndexError(Exception):
    """Base class for all bhindex errors."""


class ConfigError(BhIndexError):
    """Invalid or missing configuration."""


class FetchError(BhIndexError):
    """A network fetch failed (timeout, connection, unexpected status)."""

    def __init__(self, message: str, *, url: str | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status = status


class CloudflareChallenge(FetchError):
    """The response was a Cloudflare managed-challenge / bot-protection page.

    Terminal for the URL: do not retry. Almost always an IP-reputation issue — advise the user to
    run from a normal network, use the browser-ingest path, or supply a ``cf_clearance`` cookie.
    """


class RobotsDisallowed(FetchError):
    """The URL is disallowed by robots.txt (e.g. anything under ``/errors/``)."""


class ParseError(BhIndexError):
    """HTML did not match any known parser shape."""

    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.url = url


class StorageError(BhIndexError):
    """A database/storage operation failed."""
