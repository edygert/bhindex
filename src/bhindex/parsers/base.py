"""Shared parser helpers."""

from __future__ import annotations

import html
import re

import ftfy
from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")
# C0 (except tab/newline/CR) and C1 control characters. C1 codes like U+009D are interpreted as
# terminal escape sequences (OSC), which silently swallow following text in a terminal — they must
# never reach stored fields. ftfy removes most as a side effect of repair; this is the safety net.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _repair(text: str) -> str:
    """Repair mojibake (some feed strings are double-encoded UTF-8, e.g. ``â€™`` -> ``'``) and drop
    stray control characters that would corrupt terminal output."""
    return _CONTROL.sub("", ftfy.fix_text(text))


def strip_html(value: str | None) -> str | None:
    """Collapse an HTML fragment to readable plain text (used for abstracts/bios)."""
    if not value:
        return None
    text = BeautifulSoup(value, "lxml").get_text(" ")
    text = _WS.sub(" ", _repair(text)).strip()
    return text or None


def clean(value: str | None) -> str | None:
    """Normalize whitespace, decode HTML entities, and repair encoding (feed strings carry e.g.
    ``&#39;`` and occasional double-encoded UTF-8)."""
    if value is None:
        return None
    text = _WS.sub(" ", _repair(html.unescape(str(value)))).strip()
    return text or None
