import httpx
import pytest
import respx

from earlybird.core import http as http_module
from earlybird.core.errors import AdapterError, NotFoundError
from earlybird.core.http import USER_AGENT, HttpClient

URL = "https://example.test/api"


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_module, "DEFAULT_INTERVAL", 0.0)
    monkeypatch.setattr(http_module, "wait_exponential_jitter", lambda **_: lambda _state: 0.0)


@respx.mock
async def test_retries_transient_errors_then_succeeds() -> None:
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )
    async with HttpClient(attempts=3) as client:
        assert await client.get_json(URL) == {"ok": True}
    assert route.call_count == 2
    assert route.calls[0].request.headers["User-Agent"] == USER_AGENT


@respx.mock
async def test_404_is_not_found_and_not_retried() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    async with HttpClient(attempts=3) as client:
        with pytest.raises(NotFoundError):
            await client.get_json(URL)
    assert route.call_count == 1


@respx.mock
async def test_gives_up_with_adapter_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(500))
    async with HttpClient(attempts=2) as client:
        with pytest.raises(AdapterError):
            await client.get_json(URL)


@respx.mock
async def test_invalid_json_is_adapter_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>"))
    async with HttpClient(attempts=1) as client:
        with pytest.raises(AdapterError, match="invalid JSON"):
            await client.get_json(URL)
