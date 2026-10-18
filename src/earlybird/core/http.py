"""The only way Earlybird talks to the network: honest UA, timeouts, retries, per-host pacing."""

import asyncio
import time
from collections import defaultdict
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from earlybird import __version__
from earlybird.core.errors import AdapterError, NotFoundError

log = structlog.get_logger()

USER_AGENT = f"Earlybird/{__version__} (+https://github.com/mohangowdatdev/earlybird)"
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# Minimum seconds between requests to one host. Anything not listed gets DEFAULT_INTERVAL.
DEFAULT_INTERVAL = 0.25
HOST_INTERVALS: dict[str, float] = {
    "remotive.com": 60.0,
    "remoteok.com": 5.0,
    "himalayas.app": 2.0,
    "weworkremotely.com": 2.0,
}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


class HttpClient:
    """Async HTTP client shared by all adapters in a run."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        concurrency: int = 16,
        attempts: int = 4,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*;q=0.5"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._semaphore = asyncio.Semaphore(concurrency)
        self._attempts = attempts
        self._host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._host_last: dict[str, float] = {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def _pace(self, host: str) -> None:
        interval = HOST_INTERVALS.get(host, DEFAULT_INTERVAL)
        async with self._host_locks[host]:
            wait = self._host_last.get(host, 0.0) + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._host_last[host] = time.monotonic()

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        host = urlsplit(url).hostname or ""
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._attempts),
                wait=wait_exponential_jitter(initial=1, max=30),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            ):
                with attempt:
                    async with self._semaphore:
                        await self._pace(host)
                        response = await self._client.request(method, url, **kwargs)
                    if response.status_code == httpx.codes.NOT_FOUND:
                        raise NotFoundError(f"404 from {url}")
                    response.raise_for_status()
                    return response
        except httpx.HTTPError as exc:
            raise AdapterError(f"{method} {url} failed: {exc}") from exc
        raise AssertionError("unreachable")  # pragma: no cover

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.request("GET", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise AdapterError(f"invalid JSON from {url}") from exc

    async def post_json(self, url: str, payload: Any, **kwargs: Any) -> Any:
        response = await self.request("POST", url, json=payload, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise AdapterError(f"invalid JSON from {url}") from exc

    async def get_text(self, url: str, **kwargs: Any) -> str:
        return (await self.request("GET", url, **kwargs)).text
