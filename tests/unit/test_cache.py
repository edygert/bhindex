from bhindex.adapters.cache import FetchCache


def test_put_then_get_round_trip(tmp_path):
    cache = FetchCache(tmp_path)
    assert cache.get("https://x/a") is None

    cache.put("https://x/a", 200, '{"hello": 1}')
    hit = cache.get("https://x/a")
    assert hit is not None
    assert hit.status == 200 and hit.body == '{"hello": 1}'


def test_distinct_urls_dont_collide(tmp_path):
    cache = FetchCache(tmp_path)
    cache.put("https://x/a", 200, "A")
    cache.put("https://x/b", 200, "B")
    assert cache.get("https://x/a").body == "A"
    assert cache.get("https://x/b").body == "B"
