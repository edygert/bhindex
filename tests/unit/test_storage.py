from bhindex.core.models import MaterialKind
from bhindex.dto.contracts import EventDTO, MaterialDTO, SessionDTO, SpeakerDTO
from bhindex.storage import migrations
from bhindex.storage.db import connect, fts5_available
from bhindex.storage.repositories import Repository


def _event():
    return EventDTO(
        slug="us-2024", name="USA 2024", region="USA", year=2024,
        source_url="https://www.blackhat.com/us-24/briefings/schedule/",
        sessions=[SessionDTO(
            slug="40074", title="Breaking the Kernel",
            abstract="A new class of kernel bugs", track="OS",
            source_url="u",
            speakers=[SpeakerDTO(name="Alice Lee", affiliation="Acme")],
            materials=[MaterialDTO(title="Slides", url="https://i/x.pdf", kind=MaterialKind.SLIDES)],
        )],
    )


def test_fts5_available_in_runtime():
    conn = connect(":memory:")
    assert fts5_available(conn)


def test_apply_is_idempotent_and_versions():
    conn = connect(":memory:")
    assert migrations.apply(conn) == migrations.SCHEMA_VERSION
    assert migrations.apply(conn) == migrations.SCHEMA_VERSION
    assert migrations.current_version(conn) == migrations.SCHEMA_VERSION


def test_save_event_idempotent():
    conn = connect(":memory:")
    migrations.apply(conn)
    repo = Repository(conn)
    src = repo.get_or_create_source("wayback")

    c1 = repo.save_event(_event(), src)
    repo.commit()
    c2 = repo.save_event(_event(), src)
    repo.commit()

    assert c1.sessions == 1 and c1.materials == 1
    assert c2.materials == 0  # same material URL not re-inserted
    assert repo.stats()["sessions"] == 1


def test_reharvest_replaces_speaker_links():
    """Re-harvesting with a changed speaker identity must not accumulate stale links."""
    conn = connect(":memory:")
    migrations.apply(conn)
    repo = Repository(conn)
    src = repo.get_or_create_source("wayback")

    ev = _event()
    ev.sessions[0].speakers = [SpeakerDTO(name="Alice Lee", affiliation="Foo &amp; Bar")]
    repo.save_event(ev, src)
    ev.sessions[0].speakers = [SpeakerDTO(name="Alice Lee", affiliation="Foo & Bar")]
    repo.save_event(ev, src)
    repo.commit()

    session_id = conn.execute("SELECT id FROM sessions").fetchone()[0]
    links = conn.execute(
        "SELECT COUNT(*) FROM session_speakers WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    assert links == 1  # one current speaker, not two


def test_fts_search_hits_title_and_speaker():
    conn = connect(":memory:")
    migrations.apply(conn)
    repo = Repository(conn)
    repo.save_event(_event(), repo.get_or_create_source("wayback"))
    repo.commit()

    assert [r["title"] for r in repo.search_sessions('"kernel"')] == ["Breaking the Kernel"]
    assert repo.search_sessions('"Alice"')  # speaker indexed
