"""HIVE Scholar v2 HTTP surface."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session, select

from zoneinfo import ZoneInfo

from app.cushion import EngineConfig, availability_days, compute_cushion
from app.rollup import roll_up
from app.learn_parser import parse_source
from app.learn_store import create_track_from_spec, get_track_tree, list_tracks


def _due_to_utc(due, school_tz: str):
    """A due datetime from the UI is wall-clock in the SCHOOL zone.
    Store it as an aware UTC instant. Already-aware inputs are respected."""
    if due is None:
        return None
    if due.tzinfo is not None:
        return due.astimezone(ZoneInfo("UTC"))
    try:
        tz = ZoneInfo(school_tz)
    except Exception:
        tz = ZoneInfo("America/New_York")
    return due.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))


def _home_to_utc(dt, home_tz: str):
    """A planned-block wall time from the UI is in the user's HOME zone."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(ZoneInfo("UTC"))
    try:
        tz = ZoneInfo(home_tz)
    except Exception:
        tz = ZoneInfo("America/New_York")
    return dt.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))
from app.db import get_session
from app.models import (
    Activity, ApiKey, AwakeTime, Course, Holiday, PlannedBlock,
    ActiveTimer, Settings, Source, Task, TaskStatus, Term, TimeLog,
)


# ---- auth ------------------------------------------------------------------ #
def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: Session = Depends(get_session),
) -> ApiKey:
    key = session.exec(
        select(ApiKey).where(ApiKey.hashed_key == _hash(x_api_key), ApiKey.revoked == False)  # noqa: E712
    ).first()
    if not key:
        raise HTTPException(401, "invalid_or_revoked_api_key")
    return key


auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/keys", summary="Mint a new API key (shown once)")
def create_key(label: str = Query(...), session: Session = Depends(get_session)):
    raw = "hive_" + secrets.token_urlsafe(32)
    rec = ApiKey(label=label, hashed_key=_hash(raw))
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return {"id": rec.id, "label": rec.label, "api_key": raw}


AUTH = [Depends(require_api_key)]


# ---- learn / forge --------------------------------------------------------- #
class ParseSourceIn(BaseModel):
    text: str


class ParseSourceOut(BaseModel):
    input_type: str
    track_title: str
    role: Optional[str] = None
    modules: list[str]
    teaching_rules: list[str]
    assessment_rules: list[str]
    visual_rules: list[str]
    constraints: list[str]
    source_hash: str


class ForgeTrackIn(BaseModel):
    track_title: str
    input_type: str = "source_text"
    role: Optional[str] = None
    modules: list[str] = PydanticField(default_factory=list)
    teaching_rules: list[str] = PydanticField(default_factory=list)
    assessment_rules: list[str] = PydanticField(default_factory=list)
    visual_rules: list[str] = PydanticField(default_factory=list)
    constraints: list[str] = PydanticField(default_factory=list)
    source_hash: str = ""


learn_router = APIRouter(prefix="/learn", tags=["learn"], dependencies=AUTH)


@learn_router.post("/parse-source", response_model=ParseSourceOut)
def parse_learn_source(payload: ParseSourceIn):
    if not payload.text.strip():
        raise HTTPException(400, "text_required")
    return parse_source(payload.text)


@learn_router.get("/tracks")
def list_learning_tracks(session: Session = Depends(get_session)):
    return list_tracks(session)


@learn_router.post("/tracks", status_code=201)
def create_learning_track(payload: ForgeTrackIn, session: Session = Depends(get_session)):
    return create_track_from_spec(session, payload.dict())


@learn_router.post("/tracks/from-source", status_code=201)
def create_learning_track_from_source(payload: ParseSourceIn, session: Session = Depends(get_session)):
    if not payload.text.strip():
        raise HTTPException(400, "text_required")
    return create_track_from_spec(session, parse_source(payload.text))


@learn_router.get("/tracks/{track_id}")
def read_learning_track(track_id: int, session: Session = Depends(get_session)):
    track = get_track_tree(session, track_id)
    if not track:
        raise HTTPException(404, "track_not_found")
    return track


# ---- engine context helper -------------------------------------------------- #
def engine_ctx(session: Session):
    st = session.get(Settings, 1) or Settings(id=1)
    awake = {a.weekday: (a.start_min, a.end_min)
             for a in session.exec(select(AwakeTime)).all()}
    cfg = EngineConfig(min_block_min=st.min_block_min, awake=awake or None,
                       home_tz=st.home_tz, school_tz=st.school_tz)
    activities = session.exec(select(Activity)).all()
    planned = session.exec(select(PlannedBlock)).all()
    term = session.exec(select(Term)).first()
    holidays = session.exec(select(Holiday)).all()
    return st, cfg, activities, planned, term, holidays


# ---- courses ----------------------------------------------------------------#
courses_router = APIRouter(prefix="/courses", tags=["courses"], dependencies=AUTH)


@courses_router.get("")
def list_courses(session: Session = Depends(get_session)):
    return session.exec(select(Course)).all()


@courses_router.post("", status_code=201)
def create_course(c: Course, session: Session = Depends(get_session)):
    session.add(c); session.commit(); session.refresh(c)
    return c


@courses_router.patch("/{cid}")
def update_course(cid: int, body: dict, session: Session = Depends(get_session)):
    c = session.get(Course, cid)
    if not c:
        raise HTTPException(404)
    for k in ("name", "color", "instructor", "url", "notes", "credits"):
        if k in body:
            setattr(c, k, body[k])
    session.add(c); session.commit(); session.refresh(c)
    return c


@courses_router.delete("/{cid}", status_code=204)
def delete_course(cid: int, session: Session = Depends(get_session)):
    c = session.get(Course, cid)
    if c:
        session.delete(c); session.commit()


# ---- tasks ------------------------------------------------------------------#
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=AUTH)


class TaskIn(BaseModel):
    title: str
    notes: str = ""
    course_id: Optional[int] = None
    parent_id: Optional[int] = None
    category: str = ""
    due_at: Optional[datetime] = None
    start_date: Optional[date] = None
    time_needed_min: int = 60
    priority_flag: bool = False


class TaskPatch(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    course_id: Optional[int] = None
    parent_id: Optional[int] = None
    category: Optional[str] = None
    due_at: Optional[datetime] = None
    start_date: Optional[date] = None
    time_needed_min: Optional[int] = None
    time_spent_min: Optional[int] = None
    priority_flag: Optional[bool] = None
    status: Optional[TaskStatus] = None


@tasks_router.get("")
def list_tasks(status: Optional[TaskStatus] = None,
               session: Session = Depends(get_session)):
    stmt = select(Task)
    if status:
        stmt = stmt.where(Task.status == status)
    rows = session.exec(stmt.order_by(Task.due_at)).all()
    kids = {}
    for t in rows:
        if t.parent_id is not None:
            kids.setdefault(t.parent_id, []).append(t)
    out = []
    for t in rows:
        if t.parent_id is not None:
            continue  # children are nested under parents below
        d = {**t.model_dump(), "remaining_min": t.remaining_min,
             "direct_spent_min": t.time_spent_min}
        ch = kids.get(t.id, [])
        if ch:
            d["subtasks"] = [{**c.model_dump(), "remaining_min": c.remaining_min,
                              "direct_spent_min": c.time_spent_min} for c in ch]
            d["time_needed_min"] = sum(c.time_needed_min for c in ch)
            # parent total = subtasks' spent + time logged directly on the parent
            d["time_spent_min"] = sum(c.time_spent_min for c in ch) + t.time_spent_min
            d["remaining_min"] = max(0, d["time_needed_min"] - d["time_spent_min"])
        else:
            d["subtasks"] = []
        out.append(d)
    return out


@tasks_router.post("", status_code=201)
def create_task(payload: TaskIn, session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    data = payload.model_dump()
    data["due_at"] = _due_to_utc(data.get("due_at"), st.school_tz)
    t = Task(**data, source=Source.api)
    if t.due_at and not t.start_date:
        t.start_date = t.due_at.date() - timedelta(days=st.start_ahead_days)
    session.add(t); session.commit(); session.refresh(t)
    return t


@tasks_router.patch("/{tid}")
def update_task(tid: int, payload: TaskPatch, session: Session = Depends(get_session)):
    t = session.get(Task, tid)
    if not t:
        raise HTTPException(404)
    patch = payload.model_dump(exclude_unset=True)
    if "due_at" in patch:
        st = session.get(Settings, 1) or Settings(id=1)
        patch["due_at"] = _due_to_utc(patch["due_at"], st.school_tz)
    going_done = patch.get("status") == TaskStatus.done and t.status != TaskStatus.done
    for k, v in patch.items():
        setattr(t, k, v)
    now_utc = datetime.now(ZoneInfo("UTC"))
    t.updated_at = now_utc
    if going_done:
        t.completed_at = now_utc
        # log any not-yet-logged spent time so the streak/effort reflects it
        already = sum(lg.minutes for lg in session.exec(
            select(TimeLog).where(TimeLog.task_id == t.id)).all())
        gap = max(0, t.time_spent_min - already)
        if gap:
            session.add(TimeLog(task_id=t.id, minutes=gap, logged_at=now_utc, source="manual"))
    elif patch.get("status") == TaskStatus.todo and t.completed_at:
        t.completed_at = None  # un-completing
    session.add(t); session.commit(); session.refresh(t)
    return t


@tasks_router.post("/{tid}/log", summary="Log focused minutes on a task")
def log_time(tid: int, minutes: int = Query(..., gt=0), session: Session = Depends(get_session)):
    t = session.get(Task, tid)
    if not t:
        raise HTTPException(404)
    t.time_spent_min += minutes
    t.updated_at = datetime.now(ZoneInfo("UTC"))
    session.add(t)
    session.add(TimeLog(task_id=tid, minutes=minutes, source="timer"))
    session.commit()
    return {"task_id": tid, "time_spent_min": t.time_spent_min}


@tasks_router.delete("/{tid}", status_code=204)
def delete_task(tid: int, session: Session = Depends(get_session)):
    t = session.get(Task, tid)
    if t:
        for p in session.exec(select(PlannedBlock).where(PlannedBlock.task_id == tid)):
            session.delete(p)
        session.delete(t); session.commit()


# ---- activities --------------------------------------------------------------#
activities_router = APIRouter(prefix="/activities", tags=["activities"], dependencies=AUTH)


@activities_router.get("")
def list_activities(session: Session = Depends(get_session)):
    return session.exec(select(Activity)).all()


@activities_router.post("", status_code=201)
def create_activity(a: Activity, session: Session = Depends(get_session)):
    if not (0 <= a.start_min < a.end_min <= 1440):
        raise HTTPException(400, "bad_time_range")
    session.add(a); session.commit(); session.refresh(a)
    return a


@activities_router.delete("/{aid}", status_code=204)
def delete_activity(aid: int, session: Session = Depends(get_session)):
    a = session.get(Activity, aid)
    if a:
        session.delete(a); session.commit()


# ---- planned blocks (DO dates) ------------------------------------------------#
planned_router = APIRouter(prefix="/planned", tags=["planned"], dependencies=AUTH)


class PlanIn(BaseModel):
    task_id: int
    start_at: datetime
    end_at: datetime


class PlanPatch(BaseModel):
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    completed: Optional[bool] = None


@planned_router.get("")
def list_planned(session: Session = Depends(get_session)):
    return session.exec(select(PlannedBlock)).all()


@planned_router.post("", status_code=201)
def create_planned(p: PlanIn, session: Session = Depends(get_session)):
    if p.end_at <= p.start_at:
        raise HTTPException(400, "end_before_start")
    if not session.get(Task, p.task_id):
        raise HTTPException(404, "task_not_found")
    st = session.get(Settings, 1) or Settings(id=1)
    data = p.model_dump()
    data["start_at"] = _home_to_utc(data["start_at"], st.home_tz)
    data["end_at"] = _home_to_utc(data["end_at"], st.home_tz)
    pb = PlannedBlock(**data)
    session.add(pb); session.commit(); session.refresh(pb)
    return pb


@planned_router.patch("/{pid}")
def update_planned(pid: int, body: PlanPatch, session: Session = Depends(get_session)):
    pb = session.get(PlannedBlock, pid)
    if not pb:
        raise HTTPException(404)
    data = body.model_dump(exclude_unset=True)
    st = session.get(Settings, 1) or Settings(id=1)
    if "start_at" in data:
        data["start_at"] = _home_to_utc(data["start_at"], st.home_tz)
    if "end_at" in data:
        data["end_at"] = _home_to_utc(data["end_at"], st.home_tz)
    was_completed = pb.completed
    for k, v in data.items():
        setattr(pb, k, v)
    # completing a block logs its duration onto the task
    if data.get("completed") and not was_completed:
        t = session.get(Task, pb.task_id)
        if t:
            t.time_spent_min += int((pb.end_at - pb.start_at).total_seconds() // 60)
            t.updated_at = datetime.now()
            session.add(t)
    session.add(pb); session.commit(); session.refresh(pb)
    return pb


@planned_router.delete("/{pid}", status_code=204)
def delete_planned(pid: int, session: Session = Depends(get_session)):
    pb = session.get(PlannedBlock, pid)
    if pb:
        session.delete(pb); session.commit()


# ---- awake time ---------------------------------------------------------------#
awake_router = APIRouter(prefix="/awake", tags=["awake"], dependencies=AUTH)


class AwakeRow(BaseModel):
    weekday: int
    start_min: int
    end_min: int


@awake_router.get("")
def get_awake(session: Session = Depends(get_session)):
    return session.exec(select(AwakeTime).order_by(AwakeTime.weekday)).all()


@awake_router.put("")
def put_awake(rows: list[AwakeRow], session: Session = Depends(get_session)):
    for old in session.exec(select(AwakeTime)).all():
        session.delete(old)
    for r in rows:
        if not (0 <= r.start_min < r.end_min <= 1440):
            raise HTTPException(400, f"bad_range_weekday_{r.weekday}")
        session.add(AwakeTime(**r.model_dump()))
    session.commit()
    return {"ok": True}


# ---- term + settings -----------------------------------------------------------#
config_router = APIRouter(prefix="/config", tags=["config"], dependencies=AUTH)


@config_router.get("/settings")
def get_settings(session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    out = st.model_dump()
    out["canvas_token"] = bool(st.canvas_token)  # never echo the secret
    return out


@config_router.get("/timezones", summary="Zones grouped for the location picker")
def list_timezones(country: Optional[str] = None):
    # Friendly labels for US zones; falls back to the raw zone id elsewhere.
    US_LABELS = {
        "America/New_York": "Eastern", "America/Chicago": "Central",
        "America/Denver": "Mountain", "America/Phoenix": "Arizona (no DST)",
        "America/Los_Angeles": "Pacific", "America/Anchorage": "Alaska",
        "Pacific/Honolulu": "Hawaii",
    }
    try:
        import zoneinfo
        by_country = zoneinfo.available_timezones  # not country-mapped in stdlib
    except Exception:
        pass
    # stdlib has no country->zone map; ship a curated common set + full list.
    COUNTRIES = {
        "US": [("America/New_York", "Eastern"), ("America/Chicago", "Central"),
               ("America/Denver", "Mountain"), ("America/Phoenix", "Arizona (no DST)"),
               ("America/Los_Angeles", "Pacific"), ("America/Anchorage", "Alaska"),
               ("Pacific/Honolulu", "Hawaii")],
        "IN": [("Asia/Kolkata", "India (IST)")],
        "GB": [("Europe/London", "UK")],
        "CA": [("America/Toronto", "Eastern"), ("America/Winnipeg", "Central"),
               ("America/Edmonton", "Mountain"), ("America/Vancouver", "Pacific"),
               ("America/Halifax", "Atlantic")],
        "AU": [("Australia/Sydney", "Eastern"), ("Australia/Adelaide", "Central"),
               ("Australia/Perth", "Western")],
    }
    from zoneinfo import available_timezones
    out = {"countries": sorted(COUNTRIES.keys()),
           "zones": [{"id": z, "label": lbl} for z, lbl in COUNTRIES.get((country or "US").upper(), [])],
           "all": sorted(available_timezones())}
    return out


@config_router.put("/settings")
def put_settings(body: dict, session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    for k in ("min_block_min", "start_ahead_days", "yellow_threshold_pct",
              "day_start_min", "canvas_base_url", "canvas_token", "canvas_ics_url",
              "home_tz", "school_tz", "week_start", "country", "onboarded",
              "theme", "accent", "density", "fontscale", "default_view",
              "display_name", "canvas_autosync", "canvas_sync_hours"):
        if k in body and body[k] is not None:
            setattr(st, k, body[k])
    session.add(st); session.commit()
    return {"ok": True}


@config_router.get("/term")
def get_term(session: Session = Depends(get_session)):
    term = session.exec(select(Term)).first()
    holidays = session.exec(select(Holiday).order_by(Holiday.day)).all()
    return {"term": term, "holidays": holidays}


@config_router.put("/term")
def put_term(body: dict, session: Session = Depends(get_session)):
    term = session.exec(select(Term)).first() or Term()
    for k in ("name", "classes_start", "classes_end", "exam_end"):
        if k in body:
            v = body[k]
            setattr(term, k, date.fromisoformat(v) if isinstance(v, str) and v else (v or None))
    session.add(term); session.commit()
    return {"ok": True}


@config_router.post("/holidays", status_code=201)
def add_holiday(h: Holiday, session: Session = Depends(get_session)):
    session.add(h); session.commit(); session.refresh(h)
    return h


@config_router.delete("/holidays/{hid}", status_code=204)
def del_holiday(hid: int, session: Session = Depends(get_session)):
    h = session.get(Holiday, hid)
    if h:
        session.delete(h); session.commit()


# ---- cushion + availability ------------------------------------------------------#
cushion_router = APIRouter(prefix="/cushion", tags=["cushion"], dependencies=AUTH)


@cushion_router.get("")
def get_cushion(session: Session = Depends(get_session)):
    st, cfg, acts, planned, term, hols = engine_ctx(session)
    tasks = roll_up(session.exec(select(Task)).all())
    r = compute_cushion(tasks, cfg, acts, planned, term, hols)
    return {
        "computed_at": r.computed_at,
        "feasible": r.feasible,
        "total_cushion_min": r.total_cushion_min,
        "total_cushion_human": f"{abs(r.total_cushion_min)//60}h {abs(r.total_cushion_min)%60:02d}m"
                               + (" short" if r.total_cushion_min < 0 else ""),
        "unscheduled_task_ids": r.unscheduled_task_ids,
        "per_task": [{**c.__dict__, "level": c.level(st.yellow_threshold_pct)}
                     for c in r.per_task],
    }


@cushion_router.get("/availability")
def get_availability(start: Optional[date] = None, days: int = 7,
                     session: Session = Depends(get_session)):
    _, cfg, acts, planned, term, hols = engine_ctx(session)
    start = start or date.today()
    days = max(1, min(days, 60))
    out = availability_days(start, days, cfg, acts, planned, term, hols)
    # decorate with due counts
    tasks = session.exec(select(Task).where(Task.status == TaskStatus.todo)).all()
    for d in out:
        d["due_count"] = sum(1 for t in tasks if t.due_at and t.due_at.date().isoformat() == d["date"])
    return out


# ---- timer (single global active timer) -----------------------------------#
timer_router = APIRouter(prefix="/timer", tags=["timer"], dependencies=AUTH)


def _timer_payload(tm, session):
    t = session.get(Task, tm.task_id)
    return {
        "task_id": tm.task_id,
        "title": t.title if t else "task",
        "parent_id": t.parent_id if t else None,
        "started_at": _aware(tm.started_at).isoformat(),
        "accumulated_sec": tm.accumulated_sec,
        "paused": tm.paused,
        "running": True,
    }


@timer_router.get("", summary="Current running timer (or null)")
def get_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    return _timer_payload(tm, session) if tm else {"running": False}


@timer_router.post("/start", summary="Start timing a task/subtask")
def start_timer(task_id: int = Query(...), session: Session = Depends(get_session)):
    if not session.get(Task, task_id):
        raise HTTPException(404, "task_not_found")
    existing = session.get(ActiveTimer, 1)
    replaced = None
    if existing:
        replaced = existing.task_id
        session.delete(existing); session.commit()
    tm = ActiveTimer(id=1, task_id=task_id,
                     started_at=datetime.now(ZoneInfo("UTC")), accumulated_sec=0, paused=False)
    session.add(tm); session.commit(); session.refresh(tm)
    out = _timer_payload(tm, session); out["replaced_task_id"] = replaced
    return out


@timer_router.post("/pause", summary="Pause — bank elapsed into accumulated")
def pause_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    if not tm:
        return {"running": False}
    if not tm.paused:
        elapsed = int((datetime.now(ZoneInfo("UTC")) - _aware(tm.started_at)).total_seconds())
        tm.accumulated_sec += max(0, elapsed)
        tm.paused = True
        session.add(tm); session.commit()
    return {"paused": True, "accumulated_sec": tm.accumulated_sec}


@timer_router.post("/resume", summary="Resume a paused timer")
def resume_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    if not tm:
        return {"running": False}
    if tm.paused:
        tm.started_at = datetime.now(ZoneInfo("UTC"))
        tm.paused = False
        session.add(tm); session.commit()
    return _timer_payload(tm, session)


@timer_router.post("/stop", summary="Stop, log the minutes, clear the timer")
def stop_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    if not tm:
        return {"logged_min": 0}
    live = 0 if tm.paused else int((datetime.now(ZoneInfo("UTC")) - _aware(tm.started_at)).total_seconds())
    total_sec = tm.accumulated_sec + max(0, live)
    mins = round(total_sec / 60)
    task_id = tm.task_id
    if mins > 0:
        t = session.get(Task, task_id)
        if t:
            t.time_spent_min += mins
            session.add(t)
            session.add(TimeLog(task_id=task_id, minutes=mins, source="timer"))
    session.delete(tm); session.commit()
    return {"logged_min": mins, "task_id": task_id}


@timer_router.post("/cancel", summary="Discard the running timer — log nothing")
def cancel_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    if tm:
        session.delete(tm); session.commit()
    return {"running": False, "discarded": True}


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("UTC"))


# ---- study streak ----------------------------------------------------------#
streak_router = APIRouter(prefix="/streak", tags=["streak"], dependencies=AUTH)


@streak_router.get("", summary="Daily efficiency scores for the streak bar")
def get_streak(days: int = 9, session: Session = Depends(get_session)):
    from app.streak import current_streak, streak_window
    st = session.get(Settings, 1) or Settings(id=1)
    tasks = roll_up(session.exec(select(Task)).all())
    logs = session.exec(select(TimeLog)).all()
    window = streak_window(tasks, logs, days=max(1, min(days, 30)), home_tz=st.home_tz)
    return {
        "current": current_streak(window),
        "days": [{"day": d.day.isoformat(), "score": d.score, "level": d.level,
                  "completed": d.completed, "minutes": d.minutes, "overdue": d.overdue}
                 for d in window],
    }


@streak_router.get("/stats", summary="Plan-adherence streak + per-day heatmap data")
def get_streak_stats(session: Session = Depends(get_session)):
    from app.streak import streak_stats
    st, cfg, activities, planned, term, holidays = engine_ctx(session)
    tasks = roll_up(session.exec(select(Task)).all())
    logs = session.exec(select(TimeLog)).all()
    term_start = getattr(term, "start_date", None) if term else None
    return streak_stats(tasks, logs, planned, term_start, home_tz=st.home_tz)


# ---- analytics -------------------------------------------------------------#
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=AUTH)


@analytics_router.get("/past", summary="Past analytics aggregates for the insights page")
def analytics_past(range: str = "this_week", session: Session = Depends(get_session)):
    from app.analytics import past_analytics
    st, cfg, activities, planned, term, holidays = engine_ctx(session)
    return past_analytics(session, cfg, activities, planned, term, holidays, range)


@analytics_router.get("/future", summary="Forward-looking analytics for the insights page")
def analytics_future(range: str = "this_week", session: Session = Depends(get_session)):
    from app.analytics import future_analytics
    st, cfg, activities, planned, term, holidays = engine_ctx(session)
    return future_analytics(session, cfg, activities, planned, term, holidays, range)


@analytics_router.get("/export", summary="Export time logs as a CSV timesheet")
def analytics_export(range: str = "all", session: Session = Depends(get_session)):
    from app.analytics import timelog_export
    return timelog_export(session, range)


# ---- canvas integration ------------------------------------------------------------#
integrations_router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=AUTH)


@integrations_router.get("/canvas/status")
def canvas_status(session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    return {"configured": bool(st.canvas_base_url and st.canvas_token),
            "base_url": st.canvas_base_url,
            "ics_configured": bool(st.canvas_ics_url),
            "autosync": bool(getattr(st, "canvas_autosync", False)),
            "sync_hours": getattr(st, "canvas_sync_hours", 12) or 12,
            "last_sync": st.canvas_last_sync.isoformat() if getattr(st, "canvas_last_sync", None) else None}


@integrations_router.post("/canvas/sync")
def canvas_sync(session: Session = Depends(get_session)):
    from app.integrations import sync_canvas
    st = session.get(Settings, 1) or Settings(id=1)
    if not (st.canvas_base_url and st.canvas_token):
        raise HTTPException(400, "canvas_not_configured")
    try:
        return sync_canvas(session, st)
    except Exception as e:  # surface the reason to the UI
        raise HTTPException(502, f"canvas_sync_failed: {e}")


@integrations_router.post("/canvas/sync-ics", summary="Pull the Canvas calendar feed (no token)")
def canvas_sync_ics(session: Session = Depends(get_session)):
    from app.integrations import sync_canvas_ics
    st = session.get(Settings, 1) or Settings(id=1)
    if not st.canvas_ics_url:
        raise HTTPException(400, "ics_not_configured")
    try:
        return sync_canvas_ics(session, st)
    except Exception as e:
        raise HTTPException(502, f"ics_sync_failed: {e}")


@integrations_router.post("/canvas/import", summary="Import data collected by the browser script")
def canvas_import(payload: dict, session: Session = Depends(get_session)):
    from app.integrations import import_canvas_payload
    st = session.get(Settings, 1) or Settings(id=1)
    if not isinstance(payload, dict) or not payload.get("assignments"):
        raise HTTPException(400, "empty_payload")
    try:
        return import_canvas_payload(session, st, payload)
    except Exception as e:
        raise HTTPException(502, f"import_failed: {e}")


@integrations_router.post("/syllabus/parse", summary="Extract candidate tasks from a syllabus (PDF or text, base64)")
def syllabus_parse(payload: dict, session: Session = Depends(get_session)):
    import base64
    from app.syllabus import extract_text, parse_syllabus
    try:
        data = base64.b64decode(payload.get("data_b64") or "")
    except Exception:
        raise HTTPException(400, "bad_file_data")
    if len(data) > 8_000_000:
        raise HTTPException(413, "file_too_large")
    text = extract_text(data, payload.get("filename", "") or "")
    if not text.strip():
        return {"items": [], "chars": 0, "note": "no extractable text — is this a scanned PDF?"}
    items = parse_syllabus(text, default_year=payload.get("year"),
                           dayfirst=bool(payload.get("dayfirst")))
    return {"items": items, "chars": len(text)}


@integrations_router.post("/syllabus/import", summary="Create tasks from reviewed syllabus items")
def syllabus_import(payload: dict, session: Session = Depends(get_session)):
    from app.integrations import import_syllabus_tasks
    st = session.get(Settings, 1) or Settings(id=1)
    items = payload.get("items") or []
    if not items:
        raise HTTPException(400, "no_items")
    try:
        return import_syllabus_tasks(session, st, course_name=payload.get("course_name"), items=items)
    except Exception as e:
        raise HTTPException(502, f"import_failed: {e}")


# ---- grades ----------------------------------------------------------------#
grades_router = APIRouter(prefix="/grades", tags=["grades"], dependencies=AUTH)


def _grade_structure(session, cid):
    from app.models import GradeCategory, GradeItem
    cats = session.exec(select(GradeCategory).where(GradeCategory.course_id == cid)
                        .order_by(GradeCategory.position)).all()
    items = session.exec(select(GradeItem).where(GradeItem.course_id == cid)).all()
    by_cat = {}
    for it in items:
        by_cat.setdefault(it.category_id, []).append(
            {"id": it.id, "title": it.title, "earned": it.earned, "possible": it.possible})
    return [{"id": c.id, "name": c.name, "weight": c.weight, "items": by_cat.get(c.id, [])} for c in cats]


@grades_router.get("/summary", summary="Current grade per course (for the hub)")
def grades_summary(session: Session = Depends(get_session)):
    from app.grades import compute_grade
    from app.models import GradeCategory, GradeItem
    cats = session.exec(select(GradeCategory)).all()
    items = session.exec(select(GradeItem)).all()
    items_by_cat = {}
    for it in items:
        items_by_cat.setdefault(it.category_id, []).append({"earned": it.earned, "possible": it.possible})
    by_course = {}
    for c in cats:
        by_course.setdefault(c.course_id, []).append(
            {"name": c.name, "weight": c.weight, "items": items_by_cat.get(c.id, [])})
    out = {}
    for cid, cl in by_course.items():
        s = compute_grade(cl)
        if s["percent"] is not None:
            out[str(cid)] = {"percent": s["percent"], "letter": s["letter"]}
    return out


@grades_router.get("/{cid}", summary="Grade categories + items + summary for a course")
def get_grades(cid: int, session: Session = Depends(get_session)):
    from app.grades import compute_grade
    cat_list = _grade_structure(session, cid)
    return {"categories": cat_list, "summary": compute_grade(cat_list)}


@grades_router.put("/{cid}", summary="Replace a course's grade structure")
def put_grades(cid: int, body: dict, session: Session = Depends(get_session)):
    from app.grades import compute_grade
    from app.models import GradeCategory, GradeItem
    if not session.get(Course, cid):
        raise HTTPException(404)
    for it in session.exec(select(GradeItem).where(GradeItem.course_id == cid)).all():
        session.delete(it)
    for c in session.exec(select(GradeCategory).where(GradeCategory.course_id == cid)).all():
        session.delete(c)
    session.commit()
    cat_list = []
    for pos, c in enumerate(body.get("categories") or []):
        cat = GradeCategory(course_id=cid, name=(c.get("name") or "").strip(),
                            weight=float(c.get("weight") or 0), position=pos)
        session.add(cat); session.commit(); session.refresh(cat)
        out_items = []
        for it in (c.get("items") or []):
            title = (it.get("title") or "").strip()
            poss = float(it.get("possible") or 0)
            earn = float(it.get("earned") or 0)
            if not title and poss == 0 and earn == 0:
                continue
            session.add(GradeItem(category_id=cat.id, course_id=cid, title=title, earned=earn, possible=poss))
            out_items.append({"title": title, "earned": earn, "possible": poss})
        cat_list.append({"name": cat.name, "weight": cat.weight, "items": out_items})
    session.commit()
    return {"summary": compute_grade(cat_list)}
