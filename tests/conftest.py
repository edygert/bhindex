from __future__ import annotations

from pathlib import Path

import pytest

from bhindex.core.config import Settings, load_settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def feed_json() -> str:
    return (FIXTURES / "json" / "us24_sessions.json").read_text(encoding="utf-8")


@pytest.fixture
def temp_settings(tmp_path: Path) -> Settings:
    return load_settings(data_dir=tmp_path, request_delay=0.0, max_retries=2)
