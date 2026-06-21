"""bhindex CLI.

Commands are thin wrappers that build a ServiceContainer and call services — no business logic here,
so a future TUI/FastAPI front-end shares the exact same operations.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from bhindex import __version__
from bhindex.core.config import load_settings
from bhindex.services import ServiceContainer

app = typer.Typer(add_completion=False, help="Local-first Black Hat session metadata harvester (2016+).")

DataDir = Path | None
_data_dir_opt = typer.Option(None, "--data-dir", help="Override the data directory (DB + snapshots).")


def _container(
    data_dir: DataDir, *, ensure_schema: bool = True, **overrides: object
) -> ServiceContainer:
    if data_dir:
        overrides["data_dir"] = data_dir
    settings = load_settings(**overrides)
    return ServiceContainer(settings, ensure_schema=ensure_schema)


@app.command("init-db")
def init_db(data_dir: DataDir = _data_dir_opt) -> None:
    """Create the SQLite database, schema, and FTS index (idempotent)."""
    with _container(data_dir, ensure_schema=False) as app_:
        version = app_.init_db()
        typer.echo(f"schema ready (v{version}) at {app_.settings.db_path}")


@app.command()
def harvest(
    editions: list[str] = typer.Argument(..., help="Editions, e.g. us-24 eu-23 asia-24"),
    backfill: bool = typer.Option(True, "--backfill/--no-backfill",
                                  help="Recover 2016/2017 material links from blackhat.com/docs."),
    refresh: bool = typer.Option(False, "--refresh",
                                 help="Re-download from Wayback, ignoring the local cache."),
    data_dir: DataDir = _data_dir_opt,
) -> None:
    """Harvest one or more events from the Wayback-archived sessions.json feed (metadata only).

    Responses are cached under the data dir and reused on subsequent runs, so re-processing and
    incremental harvests don't re-download. Use --refresh to fetch fresh captures.
    """
    from rich.console import Console

    console = Console()
    total = len(editions)
    done = 0

    def render(edition: str, report) -> None:
        """Print a per-event result block (called as each edition finishes)."""
        nonlocal done
        done += 1
        colour = "green" if report.status == "ok" and not report.anomalies else (
            "red" if report.status == "error" else "yellow"
        )
        console.print(
            f"({done}/{total}) [bold {colour}]{edition:9}[/] "
            f"sessions={report.sessions_upserted:<4} speakers={report.speakers_upserted:<4} "
            f"materials={report.materials_upserted:<4} · {report.status}"
        )
        if report.status == "ok":
            console.print(
                f"          materials(feed={report.materials_from_feed} "
                f"backfill={report.materials_backfilled} unmatched={report.backfill_unmatched})  "
                f"no-abstract={report.sessions_without_abstract} "
                f"no-speakers={report.sessions_without_speakers} "
                f"no-materials={report.sessions_without_materials}",
                style="dim",
            )
        for note in report.anomalies:
            console.print(f"          ! {note}", style="yellow")
        for err in report.errors:
            console.print(f"          ! {err}", style="red")

    with _container(data_dir, refresh=refresh) as app_:
        with console.status("starting…", spinner="dots") as status:
            reports = app_.harvest.harvest_many(
                editions,
                backfill_materials=backfill,
                on_event=render,
                progress=lambda msg: status.update(msg),
            )

    clean = sum(1 for r in reports if r.status == "ok" and not r.anomalies)
    with_anomalies = sum(1 for r in reports if r.status == "ok" and r.anomalies)
    failed = sum(1 for r in reports if r.status == "error")
    console.print(
        f"\n[bold]{clean}[/] clean · [yellow]{with_anomalies}[/] with anomalies · "
        f"[red]{failed}[/] failed  of {total} editions."
    )


@app.command("ingest-file")
def ingest_file(
    path: Path = typer.Argument(..., exists=True, readable=True,
                                help="A manually-saved sessions.json (or schedule page)."),
    url: str | None = typer.Option(None, "--url", help="Original URL (sets edition + link base)."),
    data_dir: DataDir = _data_dir_opt,
) -> None:
    """Ingest a manually-saved page from disk (the offline / Save-Page-As path)."""
    with _container(data_dir) as app_:
        report = app_.harvest.ingest_file(str(path), base_url=url)
        typer.echo(
            f"{path.name}: sessions={report.sessions_upserted} "
            f"materials={report.materials_upserted} [{report.status}]"
        )


@app.command()
def stats(data_dir: DataDir = _data_dir_opt) -> None:
    """Show row counts and per-source/per-event coverage."""
    with _container(data_dir) as app_:
        overview = app_.stats.overview()
        typer.echo("  ".join(f"{k}={v}" for k, v in overview.items()))
        for row in app_.stats.by_source():
            typer.echo(f"  source {row['source']}: {row['events']} events, {row['sessions']} sessions")


@app.command()
def events(data_dir: DataDir = _data_dir_opt) -> None:
    """List harvested events."""
    with _container(data_dir) as app_:
        for row in app_.stats.events():
            typer.echo(f"{row['slug']:12} {row['name']:18} {row['sessions']:4} sessions")


@app.command()
def search(
    query: str = typer.Argument(..., help="Substring query over title/abstract/speakers/track/materials."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results to show."),
    show_all: bool = typer.Option(False, "--all", help="Show every match (ignores --limit)."),
    json_out: bool = typer.Option(
        False, "--json", help="Output full metadata of each hit as a JSON array (for piping)."
    ),
    data_dir: DataDir = _data_dir_opt,
) -> None:
    """Full-text (substring) search across harvested sessions."""
    with _container(data_dir) as app_:
        rows = app_.search.search(query, None if show_all else limit)

        if json_out:
            # Pure JSON on stdout (no summary) so it pipes cleanly into jq etc.
            details = app_.sessions.get_many([row["id"] for row in rows])
            typer.echo(json.dumps([d.model_dump(mode="json") for d in details], indent=2))
            return

        total = app_.search.count(query)
        if not rows:
            typer.echo("(no matches)")
            return
        for row in rows:
            speakers = f" — {row['speakers_text']}" if row["speakers_text"] else ""
            typer.echo(f"#{row['id']:<6} [{row['event_name']}] {row['title']}{speakers}")
        # Summary goes to stderr so it never pollutes piped/redirected result rows on stdout.
        if len(rows) < total:
            typer.echo(f"showing {len(rows)} of {total} matches (use --all or -n to see more).", err=True)
        else:
            typer.echo(
                f"{total} match{'es' if total != 1 else ''}. Use 'bhindex show <id>' for detail.",
                err=True,
            )


@app.command()
def show(
    session_id: int = typer.Argument(..., help="Session id (the #number from `search`)."),
    json_out: bool = typer.Option(
        False, "--json", help="Output the session's full metadata as a JSON object."
    ),
    data_dir: DataDir = _data_dir_opt,
) -> None:
    """Show full detail for one session: speakers, abstract, and material links."""
    with _container(data_dir) as app_:
        s = app_.sessions.get(session_id)
        if s is None:
            typer.secho(f"no session with id {session_id}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        if json_out:
            typer.echo(json.dumps(s.model_dump(mode="json"), indent=2))
            return

        typer.secho(s.title, bold=True)
        typer.echo(f"ID:       #{s.id}  (slug {s.slug})")
        typer.echo(f"Event:    {s.event_name} ({s.event_slug})")
        if s.track:
            typer.echo(f"Track:    {s.track}")
        if s.room:
            typer.echo(f"Location: {s.room}")
        if s.starts_at:
            typer.echo(f"When:     {s.starts_at}")
        typer.echo(f"Source:   {s.source_url or '(none)'}")

        if s.speakers:
            typer.echo("\nSpeakers:")
            for sp in s.speakers:
                aff = f" — {sp.affiliation}" if sp.affiliation else ""
                typer.echo(f"  {sp.name}{aff}")
                if sp.bio:
                    typer.echo(f"    {sp.bio}")
        else:
            typer.echo("\nSpeakers: none recorded")

        typer.echo("\nAbstract:")
        typer.echo(s.abstract or "(none)")

        if s.materials:
            typer.echo("\nMaterials (links only — nothing is downloaded):")
            for m in s.materials:
                redundant = not m.title or m.title in ("Material", m.url)
                title = "" if redundant else f"  ({m.title})"
                typer.echo(f"  [{m.kind.value:10}] {m.url}{title}")
        else:
            typer.echo("\nMaterials: none recorded")


@app.command()
def version() -> None:
    """Print the bhindex version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
