"""Service layer — the public backend API. The CLI (and a future TUI/FastAPI) call only this.

Nothing here exposes repositories, parsers, or fetchers to callers; those are wired in the
``ServiceContainer`` and used internally. Services are synchronous and FastAPI-friendly.
"""

from .container import ServiceContainer

__all__ = ["ServiceContainer"]
