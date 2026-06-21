"""Classify material links into a MaterialKind. Links only — nothing is ever downloaded here."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from bhindex.core.models import MaterialKind
from bhindex.dto.contracts import EventDTO, MaterialDTO

_EXT_KIND = {
    ".pdf": MaterialKind.PDF,
    ".ppt": MaterialKind.SLIDES,
    ".pptx": MaterialKind.SLIDES,
    ".key": MaterialKind.SLIDES,
    ".mp4": MaterialKind.VIDEO,
    ".m4v": MaterialKind.VIDEO,
    ".mov": MaterialKind.VIDEO,
    ".wmv": MaterialKind.VIDEO,
    ".avi": MaterialKind.VIDEO,
    ".mp3": MaterialKind.AUDIO,
    ".m4a": MaterialKind.AUDIO,
    ".zip": MaterialKind.ARCHIVE,
    ".tar": MaterialKind.ARCHIVE,
    ".gz": MaterialKind.ARCHIVE,
    ".tgz": MaterialKind.ARCHIVE,
    ".rar": MaterialKind.ARCHIVE,
}

# Material file extensions worth indexing when scanning arbitrary HTML.
MATERIAL_EXTENSIONS = tuple(_EXT_KIND.keys())


def classify(url: str, *, hint: str | None = None) -> MaterialKind:
    """Best-effort kind from a URL (and an optional label/alt hint)."""
    path = urlparse(url).path.lower()
    for ext, kind in _EXT_KIND.items():
        if path.endswith(ext):
            # Disambiguate PDFs: a "whitepaper" hint beats the generic PDF kind.
            if kind is MaterialKind.PDF and hint:
                h = hint.lower()
                if "white" in h or "paper" in h:
                    return MaterialKind.WHITEPAPER
                if "slide" in h or "presentation" in h:
                    return MaterialKind.SLIDES
            return kind
    if hint:
        h = hint.lower()
        if "video" in h:
            return MaterialKind.VIDEO
        if "audio" in h:
            return MaterialKind.AUDIO
        if "slide" in h or "presentation" in h:
            return MaterialKind.SLIDES
        if "white" in h or "paper" in h:
            return MaterialKind.WHITEPAPER
        if "code" in h or "tool" in h:
            return MaterialKind.TOOL
    return MaterialKind.OTHER


def looks_like_material(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in MATERIAL_EXTENSIONS)


# ------------------------------------------------------------------------- /docs backfill (2016/2017)
# 2016/2017 feeds carry no material links; the files live under blackhat.com/docs/<ev>/ as
# <ev>-<Presenter>-<Title>.pdf. We attach them to feed sessions by matching the filename to a
# speaker surname (primary) plus title-token overlap (fallback).

_NOISE = (
    "attendee-survey", "ciso-summit", "justification-letter", "speaking-tips",
    "schedule", "agenda", "sponsor", "registration", "report", "survey", "floorplan",
)
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "and", "for", "with", "your", "from", "into", "out", "of", "in", "on", "to",
         "a", "an", "wp", "slides", "whitepaper", "presentation", "us", "eu", "asia"}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) > 3 and t not in _STOP}


def _surname(name: str) -> str:
    parts = name.split()
    return parts[-1].lower() if parts else ""


def filename_of(url: str) -> str:
    return unquote(urlparse(url).path.rsplit("/", 1)[-1])


def is_noise_filename(filename: str) -> bool:
    low = filename.lower()
    return any(n in low for n in _NOISE)


def attach_doc_materials(event: EventDTO, urls: list[str]) -> tuple[int, list[str]]:
    """Attach archived /docs material URLs to the event's sessions. Pure; mutates ``event``.

    Returns ``(attached_count, unmatched_urls)``. Matching is by speaker surname (primary) and
    title-token overlap (tie-break / fallback). Obvious non-session files are skipped as noise.
    """
    # Pre-index sessions by speaker surname and precompute title tokens.
    by_surname: dict[str, list] = {}
    title_tokens: dict[int, set[str]] = {}
    existing: dict[int, set[str]] = {}
    for i, s in enumerate(event.sessions):
        title_tokens[i] = _tokens(s.title)
        existing[i] = {m.url for m in s.materials}
        for sp in s.speakers:
            sn = _surname(sp.name)
            if len(sn) > 2:
                by_surname.setdefault(sn, []).append(i)

    attached = 0
    unmatched: list[str] = []
    for url in urls:
        fname = filename_of(url)
        if not looks_like_material(url) or is_noise_filename(fname):
            continue
        ftoks = _tokens(fname)
        candidates = {i for sn, idxs in by_surname.items() if sn in ftoks for i in idxs}
        if candidates:
            best = max(candidates, key=lambda i: len(title_tokens[i] & ftoks))
        else:
            # No surname hit — fall back to a strong title-token overlap.
            scored = [(len(title_tokens[i] & ftoks), i) for i in range(len(event.sessions))]
            score, best = max(scored, default=(0, -1))
            if score < 3:
                unmatched.append(url)
                continue
        if url in existing[best]:
            continue
        label = "White Paper" if re.search(r"-wp\b|whitepaper|white-paper", fname, re.I) else "Slides"
        event.sessions[best].materials.append(
            MaterialDTO(title=label, url=url, kind=classify(url, hint=label))
        )
        existing[best].add(url)
        attached += 1
    return attached, unmatched
