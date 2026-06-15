"""HIVE Scholar v2 HTTP surface."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.cushion import EngineConfig, availability_days, compute_cushion
from app.db import get_session
from app.models import (
    Activity, ApiKey, AwakeTime, Course, Holiday, PlannedBlock,
    Settings, Source, Task, TaskStatus, Term,
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


# ---- engine context helper -------------------------------------------------- #
def engine_ctx(session: Session):
    st = session.get(Settings, 1) or Settings(id=1)
    awake = {a.weekday: (a.start_min, a.end_min)
             for a in session.exec(select(AwakeTime)).all()}
    cfg = EngineConfig(min_block_min=st.min_block_min, awake=awake or None)
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
    for k in ("name", "color"):
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
    category: str = ""
    due_at: Optional[datetime] = None
    start_date: Optional[date] = None
    time_needed_min: int = 60
    priority_flag: bool = False


class TaskPatch(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    course_id: Optional[int] = None
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
    return [{**t.model_dump(), "remaining_min": t.remaining_min} for t in rows]


@tasks_router.post("", status_code=201)
def create_task(payload: TaskIn, session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    t = Task(**payload.model_dump(), source=Source.api)
    if t.due_at and not t.start_date:
        t.start_date = t.due_at.date() - timedelta(days=st.start_ahead_days)
    session.add(t); session.commit(); session.refresh(t)
    return t


@tasks_router.patch("/{tid}")
def update_task(tid: int, payload: TaskPatch, session: Session = Depends(get_session)):
    t = session.get(Task, tid)
    if not t:
        raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    t.updated_at = datetime.now()
    session.add(t); session.commit(); session.refresh(t)
    return t


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
    pb = PlannedBlock(**p.model_dump())
    session.add(pb); session.commit(); session.refresh(pb)
    return pb


@planned_router.patch("/{pid}")
def update_planned(pid: int, body: PlanPatch, session: Session = Depends(get_session)):
    pb = session.get(PlannedBlock, pid)
    if not pb:
        raise HTTPException(404)
    data = body.model_dump(exclude_unset=True)
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


@config_router.put("/settings")
def put_settings(body: dict, session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    for k in ("min_block_min", "start_ahead_days", "yellow_threshold_pct",
              "day_start_min", "canvas_base_url", "canvas_token"):
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
    tasks = session.exec(select(Task)).all()
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


# ---- canvas integration ------------------------------------------------------------#
integrations_router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=AUTH)


@integrations_router.get("/canvas/status")
def canvas_status(session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    return {"configured": bool(st.canvas_base_url and st.canvas_token),
            "base_url": st.canvas_base_url}


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
