from bhindex.parsers import recent

FEED_URL = "https://www.blackhat.com/us-24/briefings/schedule/sessions.json"


def test_feed_url_for_schedule():
    assert recent.feed_url_for_schedule("https://x/us-24/briefings/schedule/") == (
        "https://x/us-24/briefings/schedule/sessions.json"
    )


def test_parse_feed(feed_json):
    ev = recent.parse_feed(feed_json, source_url=FEED_URL)
    assert ev.slug == "us-2024" and ev.year == 2024 and ev.kind.value == "recent"
    assert len(ev.sessions) == 3

    whispers = next(s for s in ev.sessions if "Whispers" in s.title)
    assert any(sp.name == "James Kettle" for sp in whispers.speakers)
    assert whispers.abstract and len(whispers.abstract) > 20
    kinds = {m.kind.value for m in whispers.materials}
    assert "slides" in kinds and "whitepaper" in kinds


def test_parse_feed_empty():
    ev = recent.parse_feed({"sessions": {}, "speakers": {}}, source_url=FEED_URL)
    assert ev.sessions == []


def test_titles_decode_html_entities():
    feed = {"sessions": {"1": {"id": 1, "title": "That Site? It&#39;s &amp; More"}}, "speakers": {}}
    ev = recent.parse_feed(feed, source_url=FEED_URL)
    assert ev.sessions[0].title == "That Site? It's & More"


def test_speaker_names_decode_html_entities():
    feed = {
        "sessions": {"1": {"id": 1, "title": "T", "speakers": [{"person_id": 9}]}},
        "speakers": {"9": {"person_id": 9, "first_name": "Leecraso", "last_name": "&nbsp;"}},
    }
    ev = recent.parse_feed(feed, source_url=FEED_URL)
    assert ev.sessions[0].speakers[0].name == "Leecraso"
