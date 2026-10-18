"""The `earlybird` command: one entry point for Make, the Procfile and GitHub Actions."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from earlybird.adapters.registry import ALL_SOURCES, BOARD_ADAPTERS
from earlybird.core.config import get_settings
from earlybird.core.logs import configure_logging
from earlybird.core.models import Visibility
from earlybird.core.registry import load_registry
from earlybird.db.engine import make_engine, upgrade
from earlybird.health.report import build_report

app = typer.Typer(
    no_args_is_help=True, add_completion=False, help="Earlybird: the early bird gets the job."
)
db_app = typer.Typer(no_args_is_help=True, help="Database commands.")
app.add_typer(db_app, name="db")

DbOption = Annotated[
    Path | None, typer.Option("--db", help="SQLite file to use instead of the configured DB.")
]


def _now() -> datetime:
    return datetime.now(UTC)


def _db_url(db: Path | None) -> str:
    return f"sqlite:///{db}" if db else get_settings().db_url


def _stale_overrides() -> dict[str, timedelta]:
    """Rate-limited boards run rarely by design; don't call them stale too early."""
    return {
        source: timedelta(minutes=adapter.MIN_INTERVAL_MINUTES) + timedelta(hours=4)
        for source, adapter in BOARD_ADAPTERS.items()
        if adapter.MIN_INTERVAL_MINUTES
    }


@app.callback()
def _setup() -> None:
    configure_logging()


@db_app.command("upgrade")
def db_upgrade(db: DbOption = None) -> None:
    """Create or migrate the database to the latest schema."""
    upgrade(_db_url(db))
    typer.echo("database is up to date")


@app.command()
def ingest(
    db: DbOption = None,
    source: Annotated[
        list[str] | None, typer.Option(help=f"Limit to sources: {', '.join(ALL_SOURCES)}")
    ] = None,
    company: Annotated[list[str] | None, typer.Option(help="Limit to registry slugs.")] = None,
    private: Annotated[
        bool, typer.Option("--private", help="Fetch private-only boards into the local DB.")
    ] = False,
) -> None:
    """Fetch sources and update the state. Default: the public plane (what Actions runs)."""
    from earlybird.ingest import run  # noqa: PLC0415 - keep CLI startup light

    settings = get_settings()
    url = _db_url(db)
    upgrade(url)
    companies = load_registry(settings.registry_path)
    if company:
        companies = [c for c in companies if c.slug in set(company)]
    unknown = set(source or []) - set(ALL_SOURCES)
    if unknown:
        raise typer.BadParameter(f"unknown source(s): {', '.join(sorted(unknown))}")
    stats = asyncio.run(
        run(
            make_engine(url),
            companies,
            sources=set(source) if source else None,
            now_fn=_now,
            timeout=settings.http_timeout_seconds,
            concurrency=settings.http_concurrency,
            visibility=Visibility.PRIVATE if private else Visibility.PUBLIC,
        )
    )
    for s in stats:
        typer.echo(
            f"{s.source:16} {s.status:8} companies={s.companies_total:<4} "
            f"failed={s.companies_failed:<3} found={s.jobs_found:<5} new={s.jobs_new}"
        )


@app.command()
def publish(
    db: Annotated[Path, typer.Option("--db", help="Public state SQLite file.")],
    out: Annotated[Path, typer.Option(help="Output directory for release assets.")] = Path("dist"),
) -> None:
    """Build the public dataset assets from the public state (refuses anything private)."""
    from earlybird.publish.dataset import write_dataset  # noqa: PLC0415

    engine = make_engine(f"sqlite:///{db}")
    now = _now()
    with engine.connect() as conn:
        report = build_report(conn, now, stale_after=_stale_overrides())
    for path in write_dataset(engine, db, out, report, now):
        typer.echo(f"wrote {path} ({path.stat().st_size:,} bytes)")


@app.command()
def health(db: DbOption = None) -> None:
    """Print the source health report as JSON. Exits 1 if any source is flagged."""
    with make_engine(_db_url(db)).connect() as conn:
        report = build_report(conn, _now(), stale_after=_stale_overrides())
    typer.echo(report.model_dump_json(indent=2))
    if report.problems:
        raise typer.Exit(1)


@app.command()
def sync() -> None:
    """Pull the latest public dataset (data-latest Release) into the local DB."""
    from earlybird.private.sync import sync as run_sync  # noqa: PLC0415

    settings = get_settings()
    upgrade(settings.db_url)
    new = asyncio.run(
        run_sync(
            make_engine(settings.db_url),
            repo=settings.dataset_repo,
            tag=settings.dataset_tag,
            cache_dir=settings.data_dir / "cache",
            timeout=settings.http_timeout_seconds,
            now=_now(),
        )
    )
    typer.echo(f"synced; {new} new jobs")


@app.command()
def schedule() -> None:
    """Run the background loop (periodic sync). Started by `make up`."""
    from earlybird.private.scheduler import run_forever  # noqa: PLC0415

    asyncio.run(run_forever(get_settings()))


@app.command()
def portal() -> None:
    """Serve the local portal (Dawn, Nest, profile builder)."""
    from earlybird.portal.app import create_app  # noqa: PLC0415

    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.portal_host, port=settings.portal_port)


@app.command()
def profile() -> None:
    """Show the current profile as JSON."""
    from earlybird.private.profile import load_profile  # noqa: PLC0415

    current = load_profile(get_settings().profile_path)
    if current is None:
        typer.echo("no profile yet: open the portal (make up) and build one at /profile")
        raise typer.Exit(1)
    typer.echo(json.dumps(current.model_dump(mode="json"), indent=2))
