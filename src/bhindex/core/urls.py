"""URL classification, edition parsing, and Wayback Machine URL builders.

Pure functions — easy to unit-test, no I/O. Keeping all of this here means the parsers and the
WaybackFetcher never hand-build archive URLs or guess event identity inconsistently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlparse, urlunparse

WAYBACK_BASE = "http://web.archive.org"
BLACKHAT_HOSTS = {"blackhat.com", "www.blackhat.com"}

_REGION_NAMES = {"us": "USA", "eu": "Europe", "asia": "Asia"}

# Modern editions (scope is 2016+): /us-24/...  /eu-23/...  /asia-25/...
_MODERN_EDITION = re.compile(r"/(us|eu|asia)-(\d{2})(?:/|$)", re.IGNORECASE)
# Also accept a bare token like "us-24" (as passed on the CLI).
_BARE_EDITION = re.compile(r"^(us|eu|asia)-(\d{2})$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class EditionInfo:
    slug: str  # canonical, e.g. "us-2024"
    region: str  # display, e.g. "USA"
    year: int  # 4-digit
    name: str  # display, e.g. "USA 2024"


def _four_digit_year(raw: str) -> int:
    if len(raw) == 4:
        return int(raw)
    n = int(raw)
    # Black Hat began in 1997; 2-digit 97-99 -> 1990s, otherwise 2000s.
    return 1900 + n if n >= 97 else 2000 + n


def parse_edition(url_or_token: str) -> EditionInfo | None:
    """Extract an event edition from a blackhat.com URL or a bare ``us-24`` token. None if absent."""
    m = _MODERN_EDITION.search(url_or_token) or _BARE_EDITION.match(url_or_token.strip())
    if not m:
        return None
    region_code, yy = m.group(1).lower(), m.group(2)
    year = _four_digit_year(yy)
    region = _REGION_NAMES.get(region_code, region_code.upper())
    return EditionInfo(slug=f"{region_code}-{year}", region=region, year=year, name=f"{region} {year}")


def edition_token(url_or_token: str) -> str | None:
    """Return the URL-form edition token (e.g. ``us-24``) used to build blackhat.com URLs."""
    m = _MODERN_EDITION.search(url_or_token) or _BARE_EDITION.match(url_or_token.strip())
    return f"{m.group(1).lower()}-{m.group(2)}" if m else None


def is_errors_path(url: str) -> bool:
    """robots.txt disallows ``/errors/`` — never crawl it."""
    return urlparse(url).path.lower().startswith("/errors/")


def normalize_url(url: str) -> str:
    """Drop fragments and trailing whitespace; keep query. Used as a dedupe key for pages."""
    p = urlparse(url.strip())
    return urlunparse((p.scheme, p.netloc, p.path, p.params, p.query, ""))


def session_anchor_id(url: str) -> str | None:
    """Recent schedules link sessions as ``schedule/#<slug>-<id>``. Return the trailing id if any."""
    frag = urlparse(url).fragment
    m = re.search(r"-(\d+)$", frag)
    return m.group(1) if m else None


def absolute(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


# --------------------------------------------------------------------------- Wayback Machine

def wayback_cdx_url(
    url_pattern: str,
    *,
    match_type: str = "prefix",
    from_year: int | None = None,
    to_year: int | None = None,
    collapse: str | None = "urlkey",
    only_ok: bool = True,
    limit: int | None = None,
    fields: tuple[str, ...] = ("timestamp", "original", "statuscode", "digest"),
) -> str:
    """Build a CDX query URL.

    The CDX server enumerates archived captures for ``url_pattern``. ``match_type=prefix`` matches
    everything under a path; ``collapse=urlkey`` keeps one row per distinct URL.
    """
    params = [
        f"url={quote(url_pattern, safe='')}",
        f"matchType={match_type}",
        "output=json",
        f"fl={','.join(fields)}",
    ]
    if collapse:
        params.append(f"collapse={collapse}")
    if only_ok:
        params.append("filter=statuscode:200")
    if from_year:
        params.append(f"from={from_year}0101")
    if to_year:
        params.append(f"to={to_year}1231")
    if limit:
        params.append(f"limit={limit}")
    return f"{WAYBACK_BASE}/cdx/search/cdx?{'&'.join(params)}"


def wayback_raw_url(timestamp: str, original_url: str) -> str:
    """Raw archived capture (``id_`` suffix) — original bytes, no Wayback toolbar/rewriting."""
    return f"{WAYBACK_BASE}/web/{timestamp}id_/{original_url}"
