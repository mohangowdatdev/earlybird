"""The adapter catalogue: maps source ids to adapter modules."""

from earlybird.adapters.ats import ashby, greenhouse, lever
from earlybird.adapters.base import AtsAdapter, BoardAdapter
from earlybird.adapters.boards import himalayas, remoteok, remotive, weworkremotely

ATS_ADAPTERS: dict[str, AtsAdapter] = {
    greenhouse.SOURCE: greenhouse,
    lever.SOURCE: lever,
    ashby.SOURCE: ashby,
}

BOARD_ADAPTERS: dict[str, BoardAdapter] = {
    remoteok.SOURCE: remoteok,
    himalayas.SOURCE: himalayas,
    weworkremotely.SOURCE: weworkremotely,
    remotive.SOURCE: remotive,
}

ALL_SOURCES: tuple[str, ...] = (*ATS_ADAPTERS, *BOARD_ADAPTERS)

# Boards whose terms forbid redistribution run on the private plane only (never published).
PRIVATE_ONLY_BOARDS: frozenset[str] = frozenset(
    source for source, adapter in BOARD_ADAPTERS.items() if not adapter.PUBLIC_OK
)
PUBLIC_SOURCES: frozenset[str] = frozenset(ALL_SOURCES) - PRIVATE_ONLY_BOARDS
