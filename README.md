# bhindex

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)

Local-first harvester and index for **Black Hat** conference session metadata. It crawls event
metadata into a local SQLite database and gives you full-text search over it — **metadata only; it
never downloads presentation files or other binaries.**

This is **Phase 1 (backend + CLI)**. A TUI and a FastAPI layer are planned to wrap the same service
layer later (see *Architecture*). Scope is intentionally **2016+** (see *Coverage*).

## Why the Wayback Machine

`blackhat.com` is fronted by a Cloudflare managed challenge that returns `403` to non-browser HTTP
clients on datacenter IPs. Rather than fight it, bhindex harvests from the **Wayback Machine**, which
is not behind Cloudflare and works from any network (including CI). Because past Black Hat events are
immutable, the archive already holds essentially all historical metadata.

## How harvesting works

- **Recent events (2016+)** publish a structured JSON feed at
  `…/<edition>/briefings/schedule/sessions.json` (the schedule page itself is a Handlebars template
  rendered from this feed). bhindex parses the feed → events, sessions, speakers, abstracts, and
  material links.
- **2016 & 2017 materials** are *not* in the feed. The files live under
  `blackhat.com/docs/<edition>/…/<edition>-<Presenter>-<Title>.pdf`. bhindex enumerates them via the
  Wayback CDX API and attaches each to its session by matching the filename to a speaker surname
  (primary) plus title-token overlap (fallback). Non-session files (surveys, letters) are skipped.
- **2018+ materials** come straight from the feed (`bh_files`, pointing at `i.blackhat.com`).
- **Manual / offline**: you can save a `sessions.json` (or any page) yourself and `ingest-file` it.

Harvesting fetches HTML/JSON only and records material **URLs** as metadata. There is no code path
from harvesting to downloading a binary.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # install runtime + dev deps
uv run bhindex --help
```

## Usage

```bash
uv run bhindex init-db                      # create the database + FTS index
uv run bhindex harvest us-24 eu-23 asia-24  # harvest one or more editions (metadata only)
uv run bhindex harvest us-17                # 2017: materials backfilled from /docs automatically
uv run bhindex harvest us-24 --refresh      # re-download, ignoring the local cache
# harvest shows a live progress monitor and a per-event validation report (anomalies / missing data).
uv run bhindex stats                        # row counts + per-source/per-event coverage
uv run bhindex events                       # list harvested events
uv run bhindex search "kernel exploit"      # full-text search; prints a #id per result
uv run bhindex show 1234                     # full detail for one session (speakers, abstract, links)

# offline / manually-saved page:
uv run bhindex ingest-file ./sessions.json --url https://www.blackhat.com/us-24/briefings/schedule/sessions.json
```

Editions are written as they appear in the URL: `us-24`, `eu-23`, `asia-24`.

Data lives under `~/.local/share/bhindex/` (override with `--data-dir` or `BHINDEX_DATA_DIR`):
`bhindex.sqlite3`, `snapshots/` (raw HTML/JSON captures for debugging + parser tests), `cache/`, and
`bhindex.log`.

**Caching.** Wayback responses (feeds + CDX enumerations) are immutable, so each is cached under
`cache/` and reused on later runs — re-processing after a parser change, and re-running a sweep, no
longer re-download. Cached editions are served from disk (no network, no delay); only new/uncached
editions are fetched, so a re-run is naturally incremental. Use `--refresh` to ignore the cache and
pull fresh captures (e.g. for a just-finalized event).

**Politeness.** The Wayback Machine rate-limits aggressively, so bhindex paces requests with a
**5 s default delay + jitter**, a single continuously-paced client across a whole multi-edition run,
and exponential backoff that honors `Retry-After` on `429`/`5xx` (throttling is surfaced live in the
progress monitor). Tune via `BHINDEX_REQUEST_DELAY`, `BHINDEX_MAX_RETRIES`, `BHINDEX_USER_AGENT`
(or `~/.config/bhindex/config.toml`). A full 2016–2025 sweep (30 editions) takes ~10–12 min at the
default delay — slower is friendlier.

## Architecture

Layered backend; the dependency rule points inward. The CLI (and a future TUI/FastAPI) call **only**
the service layer — never repositories, parsers, or fetchers directly.

```
cli ─► services ─► parsers          (recent feed parser, /docs materials matcher)
            │   └─► adapters         (HttpClient, WaybackFetcher, FileFetcher)
            └─► storage              (sqlite3 + FTS5, repositories, snapshots)
   everything ─► core / dto          (config, errors, urls, models; pydantic contracts)
```

- `ServiceContainer` is the DI root; `HarvestService`, `SearchService`, `StatsService` are the public API.
- Services are **synchronous** and FastAPI-friendly: a future web layer constructs the same container
  and calls the same methods; a TUI drives them from background workers. No core logic changes needed.
- Parsers are pure (HTML/JSON + base URL → DTOs); all network I/O lives in adapters.

## Coverage (what actually works)

| Years | Sessions + speakers + abstracts | Materials |
|---|---|---|
| 2018–2025 (us/eu/asia) | ✅ feed | ✅ feed (`i.blackhat.com`) |
| 2016–2017 | ✅ feed | ✅ backfilled from `blackhat.com/docs/` |
| ≤2015 | ❌ no JSON feed | ❌ |

Pre-2016 legacy `bh-media-archives` HTML is intentionally **out of scope** — its markup is too
heterogeneous across years to parse reliably, and is not currently needed.

## Development

```bash
uv run pytest        # unit + integration tests (fixtures are real, trimmed captures)
uv run ruff check .  # lint
```

Tests run fully offline against fixture data in `tests/fixtures/`. The integration suite pins the
Phase-1 invariant that harvesting writes only metadata + HTML snapshots, never binary files.

## License

[MIT](LICENSE) © 2026 Evan H. Dygert.

bhindex indexes only **metadata** (titles, abstracts, speakers, and links). It does not redistribute
Black Hat presentation files; all material links point back to their original sources. Respect the
source sites' terms of use and the Internet Archive's access policies when harvesting.
