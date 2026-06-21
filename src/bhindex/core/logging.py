"""Logging setup: rotating file handler + an in-memory ring buffer.

The ring buffer powers the (future) Logs TUI screen and lets tests assert on emitted records
without scraping files. ``get_log_buffer()`` returns the shared buffer.
"""

from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "bhindex"
_RING_CAPACITY = 2000


class RingBufferHandler(logging.Handler):
    """Keeps the last N formatted records in memory."""

    def __init__(self, capacity: int = _RING_CAPACITY) -> None:
        super().__init__()
        self.records: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(self.format(record))
        except Exception:  # pragma: no cover - logging must never raise
            self.handleError(record)

    def tail(self, n: int = 100) -> list[str]:
        return list(self.records)[-n:]


_ring = RingBufferHandler()
_configured = False


def get_log_buffer() -> RingBufferHandler:
    return _ring


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure_logging(log_file: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    """Idempotently attach the ring buffer (+ optional file handler) to the bhindex logger."""
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%H:%M:%S")

    if not _configured:
        _ring.setFormatter(fmt)
        logger.addHandler(_ring)
        _configured = True

    if log_file is not None and not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    return logger
