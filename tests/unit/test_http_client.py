import httpx
import pytest
import respx

from bhindex.adapters.cache import FetchCache
from bhindex.adapters.http_client import HttpClient
from bhindex.core.config import load_settings
from bhindex.core.errors import FetchError


@respx.mock
def test_retries_transient_then_succeeds(temp_settings):
    route = respx.get("https://h/a").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, text="ok")]
    )
    with HttpClient(temp_settings) as client:
        resp = client.get("https://h/a")
    assert resp.status == 200 and resp.text == "ok"
    assert route.call_count == 2


@respx.mock
def test_4xx_raises_fetcherror(temp_settings):
    respx.get("https://h/b").mock(return_value=httpx.Response(404))
    with HttpClient(temp_settings) as client, pytest.raises(FetchError):
        client.get("https://h/b")


@respx.mock
def test_network_error_raises_after_retries(temp_settings):
    respx.get("https://h/c").mock(side_effect=httpx.ConnectError("boom"))
    with HttpClient(temp_settings) as client, pytest.raises(FetchError):
        client.get("https://h/c")


@respx.mock
def test_cache_serves_second_get_without_network(temp_settings, tmp_path):
    cache = FetchCache(tmp_path / "cache")
    route = respx.get("https://h/feed").mock(return_value=httpx.Response(200, text="DATA"))
    with HttpClient(temp_settings, cache=cache) as client:
        first = client.get("https://h/feed")
        second = client.get("https://h/feed")  # should come from cache
    assert first.text == second.text == "DATA"
    assert route.call_count == 1  # network hit only once


@respx.mock
def test_refresh_bypasses_and_overwrites_cache(tmp_path):
    cache = FetchCache(tmp_path / "cache")
    cache.put("https://h/feed", 200, "OLD")
    route = respx.get("https://h/feed").mock(return_value=httpx.Response(200, text="NEW"))
    settings = load_settings(data_dir=tmp_path, request_delay=0.0, refresh=True)
    with HttpClient(settings, cache=cache) as client:
        resp = client.get("https://h/feed")
    assert resp.text == "NEW" and route.call_count == 1
    assert cache.get("https://h/feed").body == "NEW"  # cache refreshed


@respx.mock
def test_non_2xx_not_cached(temp_settings, tmp_path):
    cache = FetchCache(tmp_path / "cache")
    respx.get("https://h/missing").mock(return_value=httpx.Response(404))
    with HttpClient(temp_settings, cache=cache) as client, pytest.raises(FetchError):
        client.get("https://h/missing")
    assert cache.get("https://h/missing") is None
