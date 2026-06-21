"""Shared parser helpers."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")


def strip_html(value: str | None) -> str | None:
    """Collapse an HTML fragment to readable plain text (used for abstracts/bios)."""
    if not value:
        return None
    text = BeautifulSoup(value, "lxml").get_text(" ")
    text = _WS.sub(" ", text).strip()
    return text or None


def clean(value: str | None) -> str | None:
    """Normalize whitespace and decode HTML entities (feed strings carry e.g. ``&#39;``)."""
    if value is None:
        return None
    text = _WS.sub(" ", html.unescape(value)).strip()
    return text or None
