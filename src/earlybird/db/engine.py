"""Engine creation and migrations. Callers pass a URL; nothing here assumes SQLite."""

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url


def _ensure_sqlite_dir(url: str) -> None:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


def make_engine(url: str) -> Engine:
    _ensure_sqlite_dir(url)
    parsed = make_url(url)
    engine = create_engine(url)
    if parsed.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def upgrade(url: str) -> None:
    """Bring the database at `url` to the latest schema (idempotent)."""
    _ensure_sqlite_dir(url)
    config = Config()
    config.set_main_option("script_location", "earlybird.db:migrations")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
