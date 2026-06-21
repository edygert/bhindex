import httpx
import pytest
import respx

from bhindex.adapters.http_client import HttpClient
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
