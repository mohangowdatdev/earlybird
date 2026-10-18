"""The local portal (ADR 0010): Overview, Dawn triage, Nest board, Explore, Sources, Profile."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import Connection

from earlybird.core.config import Settings, get_settings
from earlybird.core.errors import EarlybirdError
from earlybird.core.models import RemoteType, Seniority
from earlybird.core.registry import load_registry
from earlybird.db.engine import make_engine, upgrade
from earlybird.db.schema import tracker
from earlybird.enrich.rules import remote_label, stack_tags
from earlybird.health.report import HealthReport, build_report
from earlybird.portal import queries
from earlybird.private.profile import Profile, load_profile, save_profile
from earlybird.private.scoring import PART_MAX, Bucket
from earlybird.private.sync import get_state, set_state, sync

HERE = Path(__file__).parent
DISMISS_REASONS = ("seniority", "location", "stack", "company", "salary", "domain")
TRIAGE_STATUSES = frozenset({"new", "seen", "saved", "shortlisted", "applied", "dismissed"})
NEST_STATUSES = frozenset({*queries.NEST_COLUMNS, "dismissed"})
ROLE_SUGGESTIONS = (
    "data engineer",
    "analytics engineer",
    "machine learning engineer",
    "ml engineer",
    "ai engineer",
    "data platform engineer",
    "mlops engineer",
    "data scientist",
    "data architect",
    "backend engineer",
    "platform engineer",
    "applied scientist",
)
REMOTE_HELP = {
    RemoteType.REMOTE_INDIA_OK: "Remote roles open to India, APAC or worldwide",
    RemoteType.REMOTE_UNSPECIFIED: "Remote, but the posting doesn't say where from",
    RemoteType.REMOTE_RESTRICTED: "Remote only from specific regions (US-only, EU-only…)",
    RemoteType.HYBRID: "Some days in an office, in your cities below",
    RemoteType.ONSITE: "Full-time in an office, in your cities below",
    RemoteType.UNKNOWN: "Postings that don't state a work arrangement",
}
REMOTE_ICONS = {
    RemoteType.REMOTE_INDIA_OK: "globe",
    RemoteType.REMOTE_UNSPECIFIED: "send",
    RemoteType.REMOTE_RESTRICTED: "lock",
    RemoteType.HYBRID: "hybrid",
    RemoteType.ONSITE: "building",
    RemoteType.UNKNOWN: "help",
}
SENIORITY_LABELS = {
    Seniority.INTERN: "Intern",
    Seniority.JUNIOR: "Junior",
    Seniority.MID: "Mid",
    Seniority.SENIOR: "Senior",
    Seniority.STAFF_PLUS: "Staff / Principal",
    Seniority.LEAD_MANAGER: "Lead / Manager",
    Seniority.EXECUTIVE: "Director+",
}
SOURCE_LABELS = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "remoteok": "RemoteOK",
    "weworkremotely": "We Work Remotely",
    "himalayas": "Himalayas",
    "remotive": "Remotive",
}
STATUS_LABELS = {
    "saved": "Saved",
    "shortlisted": "Shortlisted",
    "applied": "Applied",
    "interviewing": "Interviewing",
    "offer": "Offer",
    "rejected": "Rejected",
    "dismissed": "Dismissed",
    "new": "New",
    "seen": "Seen",
}
SYNC_STALE_AFTER = timedelta(hours=3)
DAWN_PAGE = 75  # a finite, decidable queue; the first sync is a backlog
EXPLORE_PAGE = 40
PREVIEW_WINDOW = timedelta(days=7)
NOON, EVENING = 12, 17


def _split(value: str) -> list[str]:
    return [part for part in (p.strip() for p in value.replace("\n", ",").split(",")) if part]


def ago(value: datetime | None, now: datetime) -> str:
    if value is None:
        return "never"
    seconds = int((now - value).total_seconds())
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return "just now"


def sparkline(values: list[int], width: int = 120, height: int = 32) -> str:
    """SVG polyline points for a small trend chart."""
    if not values:
        return ""
    if len(values) == 1:
        values = values * 2
    high = max(values) or 1
    step = width / (len(values) - 1)
    pad = 3
    return " ".join(
        f"{i * step:.1f},{height - pad - (v / high) * (height - 2 * pad):.1f}"
        for i, v in enumerate(values)
    )


def yoe_label(job: Mapping[str, Any]) -> str | None:
    low, high = job.get("yoe_min"), job.get("yoe_max")
    if low is not None and high is not None and high != low:
        return f"{low}–{high} yrs"
    if low is not None:
        return f"{low}+ yrs"
    return None


def greeting(hour: int) -> str:
    return "morning" if hour < NOON else "afternoon" if hour < EVENING else "evening"


def _set_status(
    conn: Connection, job_ids: list[str], status: str, reason: str | None, now: datetime
) -> None:
    for job_id in job_ids:
        values = {"status": status, "reason": reason, "updated_at": now}
        updated = conn.execute(tracker.update().where(tracker.c.job_id == job_id).values(**values))
        if updated.rowcount == 0:
            conn.execute(tracker.insert().values(job_id=job_id, **values))


def _profile_data(form: Any) -> dict[str, Any]:
    def text(name: str) -> str:
        value = form.get(name)
        return value if isinstance(value, str) else ""

    return {
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


def _errors(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]


def create_app(settings: Settings | None = None) -> FastAPI:  # noqa: PLR0915 - route table
    settings = settings or get_settings()
    upgrade(settings.db_url)
    engine = make_engine(settings.db_url)
    window = timedelta(days=settings.dawn_window_days)
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals.update(
        remote_label=lambda v: remote_label(RemoteType(v)),
        yoe_label=yoe_label,
        sparkline=sparkline,
        ago=ago,
        status_labels=STATUS_LABELS,
        source_label=lambda s: SOURCE_LABELS.get(s, s.title()),
        seniority_labels={s.value: label for s, label in SENIORITY_LABELS.items()},
        part_max=PART_MAX,
        reasons=DISMISS_REASONS,
    )
    app = FastAPI(title="Earlybird", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def now() -> datetime:
        return datetime.now(UTC)

    def profile_or_default() -> Profile:
        return load_profile(settings.profile_path) or Profile()

    queue_cache: dict[tuple[Any, ...], int] = {}

    def queue_count(conn: Connection, current: datetime) -> int:
        """Strong + maybe in the Dawn window; cached until data, profile or triage changes."""
        profile = load_profile(settings.profile_path)
        if profile is None:
            return 0
        key = (
            profile.version,
            get_state(conn, "last_sync_at"),
            queries.tracker_fingerprint(conn),
            current.date(),
        )
        if key not in queue_cache:
            queue_cache.clear()
            cards = queries.dawn_cards(conn, profile, now=current, window=window, since=current)
            queue_cache[key] = sum(c.score.bucket is not Bucket.EXCLUDED for c in cards)
        return queue_cache[key]

    def shell(conn: Connection) -> dict[str, Any]:
        """Context every page needs: sync status, health, nav badges."""
        current = now()
        last_sync_raw = get_state(conn, "last_sync_at")
        last_sync = datetime.fromisoformat(last_sync_raw) if last_sync_raw else None
        report: HealthReport = build_report(conn, current)
        counts = queries.status_counts(conn)
        return {
            "now": current,
            "last_sync": last_sync,
            "sync_stale": last_sync is None or current - last_sync > SYNC_STALE_AFTER,
            "report": report,
            "nav_counts": {
                "dawn": queue_count(conn, current),
                "nest": counts.get("saved", 0) + counts.get("shortlisted", 0),
            },
            "profile_name": (load_profile(settings.profile_path) or Profile()).name,
        }

    def render(request: Request, name: str, nav: str, **context: Any) -> HTMLResponse:
        with engine.connect() as conn:
            base = shell(conn)
        return templates.TemplateResponse(request, name, {**base, "nav": nav, **context})

    def partial(request: Request, name: str, **context: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"now": now(), **context})

    # ---------- pages ----------

    @app.get("/", response_model=None)
    def overview(request: Request) -> Response:
        profile = load_profile(settings.profile_path)
        if profile is None:
            return RedirectResponse("/profile?welcome=1", status_code=303)
        current = now()
        with engine.connect() as conn:
            previous = get_state(conn, "last_visit_at")
            since = datetime.fromisoformat(previous) if previous else None
            cards = queries.dawn_cards(conn, profile, now=current, window=window, since=since)
            counts = queries.status_counts(conn)
            applied_week = queries.applied_since(conn, current - timedelta(days=7))
            activity = queries.recent_activity(conn)
            history = queries.source_history(conn)
        strong = [c for c in cards if c.score.bucket is Bucket.STRONG]
        maybe = [c for c in cards if c.score.bucket is Bucket.MAYBE]
        return render(
            request,
            "overview.html",
            "overview",
            greeting=greeting(datetime.now().astimezone().hour),
            profile=profile,
            strong=strong,
            maybe_count=len(maybe),
            fresh=sum(c.is_new for c in cards if c.score.bucket is not Bucket.EXCLUDED),
            top=(strong + maybe)[:5],
            counts=counts,
            applied_week=applied_week,
            activity=activity,
            history=history,
            pipeline=[(s, counts.get(s, 0)) for s in queries.NEST_COLUMNS],
        )

    @app.get("/dawn", response_model=None)
    def dawn(
        request: Request,
        *,
        bucket: str = "queue",
        remote: str | None = None,
        source: str | None = None,
        q: str | None = None,
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
                window=window,
                since=since,
                remote=remote or None,
                source=source or None,
                query=q or None,
            )
        by_bucket = {b: [c for c in cards if c.score.bucket is b] for b in Bucket}
        if bucket in {b.value for b in Bucket}:
            visible = by_bucket[Bucket(bucket)]
        else:
            bucket = "queue"
            visible = by_bucket[Bucket.STRONG] + by_bucket[Bucket.MAYBE]
        return render(
            request,
            "dawn.html",
            "dawn",
            cards=visible[:limit],
            hidden=max(0, len(visible) - limit),
            next_limit=limit + DAWN_PAGE,
            total=len(visible),
            bucket=bucket,
            bucket_counts={b.value: len(v) for b, v in by_bucket.items()},
            filters={"remote": remote or "", "source": source or "", "q": q or ""},
            remote_types=list(RemoteType),
            window_days=settings.dawn_window_days,
        )

    @app.get("/jobs/{job_id}/detail", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: str) -> HTMLResponse:
        with engine.connect() as conn:
            card = queries.job_detail(conn, job_id, profile_or_default())
        if card is None:
            return HTMLResponse("<div class='empty'>This job is gone.</div>", status_code=404)
        return partial(request, "_detail.html", card=card)

    @app.post("/triage")
    def triage(
        job_ids: Annotated[str, Form()],
        status: Annotated[str, Form()],
        reason: Annotated[str | None, Form()] = None,
    ) -> JSONResponse:
        if status not in TRIAGE_STATUSES:
            return JSONResponse({"ok": False, "error": "unknown status"}, status_code=400)
        ids = _split(job_ids)
        with engine.begin() as conn:
            _set_status(conn, ids, status, reason, now())
        return JSONResponse({"ok": True, "status": status, "count": len(ids)})

    @app.get("/nest", response_class=HTMLResponse)
    def nest(request: Request) -> HTMLResponse:
        with engine.connect() as conn:
            columns = queries.nest_cards(conn, profile_or_default())
        return render(request, "nest.html", "nest", columns=columns)

    @app.get("/nest/{job_id}/drawer", response_class=HTMLResponse)
    def nest_drawer(request: Request, job_id: str) -> HTMLResponse:
        with engine.connect() as conn:
            card = queries.job_detail(conn, job_id, profile_or_default())
        if card is None:
            return HTMLResponse("<div class='empty'>This job is gone.</div>", status_code=404)
        return partial(
            request, "_nest_drawer.html", card=card, statuses=[*queries.NEST_COLUMNS, "dismissed"]
        )

    @app.post("/nest/{job_id}")
    def nest_update(
        job_id: str,
        status: Annotated[str | None, Form()] = None,
        note: Annotated[str | None, Form()] = None,
    ) -> JSONResponse:
        if status is not None and status not in NEST_STATUSES:
            return JSONResponse({"ok": False, "error": "unknown status"}, status_code=400)
        with engine.begin() as conn:
            if status is not None:
                _set_status(conn, [job_id], status, None, now())
            if note is not None:
                conn.execute(
                    tracker.update().where(tracker.c.job_id == job_id).values(note=note.strip())
                )
        return JSONResponse({"ok": True})

    @app.get("/explore", response_class=HTMLResponse)
    def explore(
        request: Request,
        *,
        q: str = "",
        remote: str = "",
        source: str = "",
        bucket: str = "",
        page: int = 1,
    ) -> HTMLResponse:
        with engine.connect() as conn:
            cards = queries.explore_cards(
                conn,
                profile_or_default(),
                query=q or None,
                remote=remote or None,
                source=source or None,
            )
        if bucket in {b.value for b in Bucket}:
            cards = [c for c in cards if c.score.bucket.value == bucket]
        page = max(1, page)
        start = (page - 1) * EXPLORE_PAGE
        return render(
            request,
            "explore.html",
            "explore",
            cards=cards[start : start + EXPLORE_PAGE],
            total=len(cards),
            page=page,
            pages=max(1, -(-len(cards) // EXPLORE_PAGE)),
            filters={"q": q, "remote": remote, "source": source, "bucket": bucket},
            remote_types=list(RemoteType),
        )

    @app.get("/sources", response_class=HTMLResponse)
    def sources(request: Request) -> HTMLResponse:
        names = (
            {c.slug: c.name for c in load_registry(settings.registry_path, include_excluded=True)}
            if settings.registry_path.exists()
            else {}
        )
        with engine.connect() as conn:
            history = queries.source_history(conn)
            companies = queries.companies(conn)
        return render(
            request, "sources.html", "sources", history=history, companies=companies, names=names
        )

    def profile_page(
        request: Request, profile: Profile, *, errors: list[str], saved: bool, welcome: bool
    ) -> HTMLResponse:
        registry = load_registry(settings.registry_path) if settings.registry_path.exists() else []
        return render(
            request,
            "profile.html",
            "profile",
            profile=profile,
            errors=errors,
            saved=saved,
            welcome=welcome,
            remote_options=[(r, REMOTE_HELP[r], REMOTE_ICONS[r]) for r in RemoteType],
            seniorities=list(SENIORITY_LABELS.items()),
            role_suggestions=list(ROLE_SUGGESTIONS),
            skill_suggestions=stack_tags(),
            company_suggestions=[{"value": c.slug, "label": c.name} for c in registry],
        )

    @app.get("/profile", response_class=HTMLResponse)
    def profile_form(request: Request, welcome: bool = False, saved: bool = False) -> HTMLResponse:
        profile = load_profile(settings.profile_path)
        return profile_page(
            request,
            profile or Profile(),
            errors=[],
            saved=saved,
            welcome=welcome or profile is None,
        )

    @app.post("/profile", response_model=None)
    async def profile_save(request: Request) -> Response:
        data = _profile_data(await request.form())
        try:
            profile = Profile.model_validate(data)
        except ValidationError as exc:
            draft = Profile.model_construct(**data)
            return profile_page(request, draft, errors=_errors(exc), saved=False, welcome=False)
        save_profile(profile, settings.profile_path)
        return RedirectResponse("/profile?saved=1", status_code=303)

    @app.post("/profile/preview", response_class=HTMLResponse)
    async def profile_preview(request: Request) -> HTMLResponse:
        try:
            profile = Profile.model_validate(_profile_data(await request.form()))
        except ValidationError as exc:
            return partial(request, "_preview.html", errors=_errors(exc))
        current = now()
        with engine.connect() as conn:
            cards = queries.dawn_cards(
                conn, profile, now=current, window=max(window, PREVIEW_WINDOW), since=current
            )
        counts = {b.value: sum(c.score.bucket is b for c in cards) for b in Bucket}
        return partial(
            request,
            "_preview.html",
            errors=[],
            counts=counts,
            total=len(cards),
            top=[c for c in cards if c.score.bucket is not Bucket.EXCLUDED][:4],
            days=max(window, PREVIEW_WINDOW).days,
        )

    # ---------- actions & API ----------

    @app.post("/sync")
    async def sync_now() -> JSONResponse:
        try:
            new = await sync(
                engine,
                repo=settings.dataset_repo,
                tag=settings.dataset_tag,
                cache_dir=settings.data_dir / "cache",
                timeout=settings.http_timeout_seconds,
                now=now(),
            )
        except EarlybirdError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
        return JSONResponse({"ok": True, "new_jobs": new})

    @app.get("/health")
    def health_json() -> dict[str, Any]:
        with engine.connect() as conn:
            base = shell(conn)
        report: HealthReport = base["report"]
        last_sync: datetime | None = base["last_sync"]
        return {
            "ok": not report.problems,
            "last_sync_at": last_sync.isoformat() if last_sync else None,
            "report": report.model_dump(mode="json"),
        }

    return app
