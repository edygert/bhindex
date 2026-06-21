from bhindex.core.models import MaterialKind
from bhindex.dto.contracts import EventDTO, SessionDTO, SpeakerDTO
from bhindex.parsers import materials
from bhindex.parsers.base import clean, strip_html


def test_repairs_mojibake_and_strips_control_chars():
    # Double-encoded UTF-8 (cp1252 mis-decode); the closing-quote mojibake embeds a C1 control
    # char (\x9d) that a terminal treats as an escape and silently swallows following text.
    raw = "founding member of â€œThe Diana Initiativeâ€\x9d. Iâ€™ll talk"
    out = clean(raw)
    assert '"The Diana Initiative"' in out
    assert "I'll talk" in out
    assert not any(0x80 <= ord(c) <= 0x9F for c in out)  # no C1 controls survive
    # same repair through the HTML path
    assert strip_html(f"<p>{raw}</p>").endswith("I'll talk")


def test_preserves_legitimate_accented_text():
    assert clean("Fabian Bäumer") == "Fabian Bäumer"
    assert clean("Jens Müller") == "Jens Müller"


def test_classify_by_extension_and_hint():
    assert materials.classify("http://x/a.pdf") == MaterialKind.PDF
    assert materials.classify("http://x/a.pdf", hint="White Paper") == MaterialKind.WHITEPAPER
    assert materials.classify("http://x/a.pdf", hint="Slides") == MaterialKind.SLIDES
    assert materials.classify("http://x/a.m4v") == MaterialKind.VIDEO
    assert materials.classify("http://x/a.mp3") == MaterialKind.AUDIO
    assert materials.classify("http://x/a.zip") == MaterialKind.ARCHIVE


def test_looks_like_material():
    assert materials.looks_like_material("http://x/a.pdf")
    assert not materials.looks_like_material("http://x/page.html")


def _event_with_session(title, speaker=None):
    return EventDTO(
        slug="us-2017", name="USA 2017", source_url="u",
        sessions=[SessionDTO(
            slug="1", title=title, source_url="u",
            speakers=[SpeakerDTO(name=speaker)] if speaker else [],
        )],
    )


def test_backfill_matches_by_surname():
    ev = _event_with_session("Web Timing Attacks", speaker="James Kettle")
    url = "https://www.blackhat.com/docs/us-17/us-17-Kettle-Web-Timing-Attacks.pdf"
    attached, unmatched = materials.attach_doc_materials(ev, [url])
    assert attached == 1 and not unmatched
    assert ev.sessions[0].materials[0].url == url


def test_backfill_matches_by_title_when_no_surname():
    ev = _event_with_session("Exploiting Network Printers", speaker="Anon")
    url = "https://www.blackhat.com/docs/us-17/us-17-Mueller-Exploiting-Network-Printers.pdf"
    attached, _ = materials.attach_doc_materials(ev, [url])
    assert attached == 1


def test_backfill_skips_noise_and_whitepaper_kind():
    ev = _event_with_session("Web Timing Attacks", speaker="James Kettle")
    noise = "https://www.blackhat.com/docs/us-17/2017-black-hat-attendee-survey.pdf"
    wp = "https://www.blackhat.com/docs/us-17/us-17-Kettle-Web-Timing-Attacks-wp.pdf"
    attached, unmatched = materials.attach_doc_materials(ev, [noise, wp])
    assert attached == 1  # noise skipped, whitepaper attached
    assert ev.sessions[0].materials[0].kind == MaterialKind.WHITEPAPER
