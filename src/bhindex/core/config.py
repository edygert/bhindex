"""Application settings.

Resolution order (pydantic-settings): explicit kwargs > env vars (``BHINDEX_*``) > values in
``~/.config/bhindex/config.toml`` > defaults. Paths follow the XDG base-dir spec.

Scope note: bhindex harvests from the Wayback Machine (no Cloudflare) or from manually-saved HTML.
It runs once per Black Hat event, so there is no concurrency or large-scale-scrape machinery here —
just a polite delay and a couple of retries for the occasional Wayback hiccup.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_UA = "bhindex/0.1 (+local metadata indexer; contact via config)"


def _xdg(env: str, default_sub: str) -> Path:
    base = os.environ.get(env)
    root = Path(base) if base else Path.home() / default_sub
    return root / "bhindex"


def _default_data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def _default_config_file() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "config.toml"


def _toml_source() -> dict[str, Any]:
    path = _default_config_file()
    if path.is_file():
        with path.open("rb") as fh:
            return tomllib.load(fh)
    return {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BHINDEX_", extra="ignore")

    # storage
    data_dir: Path = Field(default_factory=_default_data_dir)

    # politeness for the Wayback Machine (it rate-limits aggressively; be gentle)
    request_delay: float = 5.0  # seconds between requests (a small random jitter is added)
    max_retries: int = 4  # retries on timeout / 5xx / 429, with exponential backoff + Retry-After
    timeout: float = 30.0
    user_agent: str = DEFAULT_UA

    # caching: reuse stored Wayback responses instead of re-downloading. refresh=True re-fetches.
    refresh: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bhindex.sqlite3"

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "bhindex.log"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


def load_settings(**overrides: Any) -> Settings:
    """Build Settings from TOML + env + overrides (overrides win)."""
    merged: dict[str, Any] = {**_toml_source(), **overrides}
    return Settings(**merged)
