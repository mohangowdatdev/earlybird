"""Adapter contracts. An adapter is a module exposing `SOURCE`, a pure `parse`, and `fetch`.

`parse` turns a saved payload into Jobs (tested against real fixtures); `fetch` does the network
call through the shared HttpClient and delegates to `parse`. Adapters never touch storage.
"""

from typing import Protocol

from earlybird.core.http import HttpClient
from earlybird.core.models import AtsRef, Company, Job


class AtsAdapter(Protocol):
    @property
    def SOURCE(self) -> str: ...  # noqa: N802 - module constant

    async def fetch(self, http: HttpClient, company: Company, ref: AtsRef) -> list[Job]: ...


class BoardAdapter(Protocol):
    @property
    def SOURCE(self) -> str: ...  # noqa: N802 - module constant

    @property
    def MIN_INTERVAL_MINUTES(self) -> int: ...  # noqa: N802 - module constant

    @property
    def PUBLIC_OK(self) -> bool: ...  # noqa: N802 - module constant; False = private plane only

    async def fetch(self, http: HttpClient) -> list[Job]: ...
