"""The local portal (ADR 0010): Dawn for triage, Nest for applications, the profile builder."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import Connection

from earlybird.core.config import Settings, get_settings
from earlybird.core.models import RemoteType, Seniority
from earlybird.core.registry import load_registry
from earlybird.db.engine import make_engine, upgrade
from earlybird.db.schema import tracker
from earlybird.enrich.rules import remote_label, stack_tags
from earlybird.health.report import HealthReport, build_report
from earlybird.portal import queries
from earlybird.private.profile import Profile, load_profile, save_profile
from earlybird.private.scoring import Bucket
from earlybird.private.sync import get_state, set_state

DISMISS_REASONS = ("seniority", "location", "stack", "company", "salary", "domain")
TRIAGE_STATUSES = frozenset({"new", "seen", "saved", "dismissed", "applied", "shortlisted"})
NEST_STATUSES = frozenset({*queries.NEST_COLUMNS, "dismissed"})
ROLE_SUGGESTIONS = (
    "data engineer",
    "analytics engineer",
    "machine learning engineer",
    "ai engineer",
    "ml engineer",
    "data platform engineer",
    "mlops engineer",
    "data scientist",
    "backend engineer",
)
SYNC_STALE_AFTER = timedelta(hours=3)
DAWN_PAGE = 75  # a finite, decidable queue; the first sync is a backlog


def _split(value: str) -> list[str]:
    return [part for part in (p.strip() for p in value.replace("\n", ",").split(",")) if part]


def _ago(value: datetime | None, now: datetime) -> str:
    if value is None:
        return "never"
    seconds = int((now - value).total_seconds())
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return "just now"


def _set_status(
    conn: Connection, job_ids: list[str], status: str, reason: str | None, now: datetime
) -> None:
    for job_id in job_ids:
        values = {"status": status, "reason": reason, "updated_at": now}
        updated = conn.execute(tracker.update().where(tracker.c.job_id == job_id).values(**values))
        if updated.rowcount == 0:
            conn.execute(tracker.insert().values(job_id=job_id, **values))


def create_app(settings: Settings | None = None) -> FastAPI:  # noqa: PLR0915 - route table
    settings = settings or get_settings()
    upgrade(settings.db_url)
    engine = make_engine(settings.db_url)
    templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
    templates.env.globals.update(remote_label=lambda v: remote_label(RemoteType(v)))
    app = FastAPI(title="Earlybird", docs_url=None, redoc_url=None)

    def now() -> datetime:
        return datetime.now(UTC)

    def health(conn: Connection) -> tuple[HealthReport, datetime | None]:
        last_sync = get_state(conn, "last_sync_at")
        return build_report(conn, now()), datetime.fromisoformat(last_sync) if last_sync else None

    def render(request: Request, name: str, **context: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"now": now(), "ago": _ago, **context})

    @app.get("/")
    def index() -> RedirectResponse:
        target = "/dawn" if settings.profile_path.exists() else "/profile?welcome=1"
        return RedirectResponse(target, status_code=303)

    @app.get("/dawn", response_class=HTMLResponse)
    def dawn(
        request: Request,
        *,
        remote: str | None = None,
        source: str | None = None,
        q: str | None = None,
        show: str | None = None,
        limit: int = DAWN_PAGE,
    ) -> Response:
        profile = load_profile(settings.profile_path)
        if profile is None:
            return RedirectResponse("/profile?welcome=1", status_code=303)
        current = now()
        with engine.begin() as conn:
            previous = get_state(conn, "last_visit_at")
            since = datetime.fromisoformat(previous) if previous else None
            set_state(conn, "last_visit_at", current.isoformat())
            cards = queries.dawn_cards(
                conn,
                profile,
                now=current,
                window=timedelta(days=settings.dawn_window_days),
                since=since,
                remote=remote or None,
                source=source or None,
                query=q or None,
            )
            report, last_sync = health(conn)
        visible = [c for c in cards if (c.score.bucket is Bucket.EXCLUDED) == (show == "excluded")]
        return render(
            request,
            "dawn.html",
            cards=visible[:limit],
            hidden=max(0, len(visible) - limit),
            next_limit=limit + DAWN_PAGE,
            strong=sum(c.score.bucket is Bucket.STRONG for c in cards),
            maybe=sum(c.score.bucket is Bucket.MAYBE for c in cards),
            excluded=sum(c.score.bucket is Bucket.EXCLUDED for c in cards),
            show=show,
            filters={"remote": remote or "", "source": source or "", "q": q or ""},
            remote_types=list(RemoteType),
            sources=sorted({s.source for s in report.sources}),
            report=report,
            last_sync=last_sync,
            sync_stale=last_sync is None or current - last_sync > SYNC_STALE_AFTER,
            reasons=DISMISS_REASONS,
        )

    @app.post("/triage", response_class=HTMLResponse)
    def triage(
        request: Request,
        job_ids: Annotated[str, Form()],
        status: Annotated[str, Form()],
        reason: Annotated[str | None, Form()] = None,
    ) -> HTMLResponse:
        if status not in TRIAGE_STATUSES:
            return HTMLResponse("unknown status", status_code=400)
        ids = _split(job_ids)
        with engine.begin() as conn:
            _set_status(conn, ids, status, reason, now())
        if status in ("new", "seen"):
            return HTMLResponse("")
        return render(request, "_triaged.html", status=status, reason=reason, job_ids=job_ids)

    @app.get("/nest", response_class=HTMLResponse)
    def nest(request: Request) -> HTMLResponse:
        profile = load_profile(settings.profile_path) or Profile()
        with engine.connect() as conn:
            columns = queries.nest_cards(conn, profile)
        return render(request, "nest.html", columns=columns)

    @app.post("/nest/{job_id}")
    def nest_update(
        job_id: str,
        status: Annotated[str | None, Form()] = None,
        note: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        with engine.begin() as conn:
            if status in NEST_STATUSES:
                _set_status(conn, [job_id], status, None, now())
            if note is not None:
                conn.execute(
                    tracker.update().where(tracker.c.job_id == job_id).values(note=note.strip())
                )
        return RedirectResponse("/nest", status_code=303)

    @app.get("/jobs", response_class=HTMLResponse)
    def all_jobs(request: Request, q: str = "") -> HTMLResponse:
        profile = load_profile(settings.profile_path) or Profile()
        with engine.connect() as conn:
            cards = queries.search(conn, profile, q) if q else []
        return render(request, "jobs.html", cards=cards, q=q, reasons=DISMISS_REASONS)

    def profile_page(
        request: Request, profile: Profile, *, errors: list[str], saved: bool, welcome: bool
    ) -> HTMLResponse:
        companies = load_registry(settings.registry_path) if settings.registry_path.exists() else []
        return render(
            request,
            "profile.html",
            profile=profile,
            errors=errors,
            saved=saved,
            welcome=welcome,
            remote_types=list(RemoteType),
            seniorities=[s for s in Seniority if s is not Seniority.UNKNOWN],
            role_suggestions=ROLE_SUGGESTIONS,
            skill_suggestions=stack_tags(),
            companies=companies,
        )

    @app.get("/profile", response_class=HTMLResponse)
    def profile_form(request: Request, welcome: bool = False, saved: bool = False) -> HTMLResponse:
        profile = load_profile(settings.profile_path) or Profile()
        return profile_page(request, profile, errors=[], saved=saved, welcome=welcome)

    @app.post("/profile", response_model=None)
    async def profile_save(request: Request) -> Response:
        form = await request.form()

        def text(name: str) -> str:
            value = form.get(name)
            return value if isinstance(value, str) else ""

        data: dict[str, Any] = {
            "name": text("name"),
            "yoe": text("yoe") or 0,
            "role_families": _split(text("role_families")),
            "skills_must": _split(text("skills_must")),
            "skills_nice": _split(text("skills_nice")),
            "remote_types": form.getlist("remote_types"),
            "cities": _split(text("cities")),
            "seniorities": form.getlist("seniorities"),
            "exclude_title_patterns": _split(text("exclude_title_patterns")),
            "watchlist": _split(text("watchlist")),
            "min_salary_usd": text("min_salary_usd") or None,
            "chirp_daily_cap": text("chirp_daily_cap") or 5,
        }
        try:
            profile = Profile.model_validate(data)
        except ValidationError as exc:
            errors = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
            draft = Profile.model_construct(**data)
            return profile_page(request, draft, errors=errors, saved=False, welcome=False)
        save_profile(profile, settings.profile_path)
        return RedirectResponse("/profile?saved=1", status_code=303)

    @app.get("/health")
    def health_json() -> dict[str, Any]:
        with engine.connect() as conn:
            report, last_sync = health(conn)
        return {
            "ok": not report.problems,
            "last_sync_at": last_sync.isoformat() if last_sync else None,
            "report": report.model_dump(mode="json"),
        }

    return app
