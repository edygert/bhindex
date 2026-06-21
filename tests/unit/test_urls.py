from bhindex.core import urls


def test_parse_edition_from_url():
    e = urls.parse_edition("https://www.blackhat.com/us-24/briefings/schedule/")
    assert (e.slug, e.year, e.region, e.name) == ("us-2024", 2024, "USA", "USA 2024")


def test_parse_edition_bare_token_and_regions():
    assert urls.parse_edition("eu-23").name == "Europe 2023"
    assert urls.parse_edition("asia-24").name == "Asia 2024"
    assert urls.edition_token("us-24") == "us-24"
    assert urls.edition_token("https://www.blackhat.com/eu-23/x") == "eu-23"


def test_parse_edition_none():
    assert urls.parse_edition("https://example.com/") is None
    assert urls.edition_token("not-an-edition") is None


def test_is_errors_path():
    assert urls.is_errors_path("https://www.blackhat.com/errors/404.html")
    assert not urls.is_errors_path("https://www.blackhat.com/us-24/briefings/")


def test_session_anchor_id():
    assert urls.session_anchor_id(".../schedule/#living-off-copilot-40074") == "40074"
    assert urls.session_anchor_id(".../schedule/") is None


def test_wayback_builders():
    cdx = urls.wayback_cdx_url("blackhat.com/docs/us-17/", from_year=2017, to_year=2018)
    assert "cdx/search/cdx" in cdx and "matchType=prefix" in cdx and "from=20170101" in cdx
    raw = urls.wayback_raw_url("20240503", "https://www.blackhat.com/us-24/x")
    assert raw == "http://web.archive.org/web/20240503id_/https://www.blackhat.com/us-24/x"
