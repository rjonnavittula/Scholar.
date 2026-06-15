"""HTTP surface: auth + routers for tasks, courses, ingestion, and cushion.

Clean REST in the spirit of Vikunja; FastAPI gives you the Swagger UI at /docs
and ReDoc at /redoc for free.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.cushion import availability_days, compute_cushion
from app.db import get_session
from app.models import (
    ApiKey,
    Commitment,
    Course,
    Event,
    Task,
    TaskSource,
    TaskStatus,
)


# --------------------------------------------------------------------------- #
# Auth — X-API-Key header, compared against sha256 hashes in the DB.
# --------------------------------------------------------------------------- #
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
        raise HTTPException(status_code=401, detail="invalid_or_revoked_api_key")
    return key


auth_router = APIRouter(prefix="/auth", tags=["auth"])


class ApiKeyCreated(BaseModel):
    id: int
    label: str
    api_key: str  # shown exactly once


@auth_router.post("/keys", response_model=ApiKeyCreated, summary="Mint a new API key")
def create_key(label: str = Query(...), session: Session = Depends(get_session)):
    raw = "hive_" + secrets.token_urlsafe(32)
    rec = ApiKey(label=label, hashed_key=_hash(raw))
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return ApiKeyCreated(id=rec.id, label=rec.label, api_key=raw)


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_api_key)])


class TaskIn(BaseModel):
    title: str
    notes: str = ""
    course_id: Optional[int] = None
    due_at: Optional[datetime] = None
    time_needed_min: int = 0
    time_spent_min: int = 0
    priority: int = 0
    status: TaskStatus = TaskStatus.todo


class TaskUpdate(BaseModel):
    """Partial update — every field optional, so PATCH {'status':'done'} works."""
    title: Optional[str] = None
    notes: Optional[str] = None
    course_id: Optional[int] = None
    due_at: Optional[datetime] = None
    time_needed_min: Optional[int] = None
    time_spent_min: Optional[int] = None
    priority: Optional[int] = None
    status: Optional[TaskStatus] = None


@tasks_router.get("", summary="List tasks")
def list_tasks(
    status: Optional[TaskStatus] = None,
    course_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    stmt = select(Task)
    if status:
        stmt = stmt.where(Task.status == status)
    if course_id:
        stmt = stmt.where(Task.course_id == course_id)
    return session.exec(stmt.order_by(Task.due_at)).all()


@tasks_router.post("", status_code=201, summary="Create a task")
def create_task(payload: TaskIn, session: Session = Depends(get_session)):
    task = Task(**payload.model_dump(), source=TaskSource.api)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@tasks_router.patch("/{task_id}", summary="Update a task (partial)")
def update_task(task_id: int, payload: TaskUpdate, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task_not_found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@tasks_router.delete("/{task_id}", status_code=204, summary="Delete a task")
def delete_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if task:
        session.delete(task)
        session.commit()


# --------------------------------------------------------------------------- #
# Courses
# --------------------------------------------------------------------------- #
courses_router = APIRouter(prefix="/courses", tags=["courses"], dependencies=[Depends(require_api_key)])


@courses_router.get("", summary="List courses")
def list_courses(session: Session = Depends(get_session)):
    return session.exec(select(Course)).all()


@courses_router.post("", status_code=201, summary="Create a course")
def create_course(course: Course, session: Session = Depends(get_session)):
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


# --------------------------------------------------------------------------- #
# Ingestion — normalized LMS payloads (the Python client does the LMS call).
# --------------------------------------------------------------------------- #
ingest_router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(require_api_key)])


class CanvasItem(BaseModel):
    external_id: str
    title: str
    course_name: str
    course_external_id: Optional[str] = None
    due_at: Optional[datetime] = None
    notes: str = ""
    time_needed_min: int = 60  # heuristic default; refine per assignment type


@ingest_router.post("/canvas", summary="Upsert assignments pulled from Canvas/LMS")
def ingest_canvas(items: list[CanvasItem], session: Session = Depends(get_session)):
    created, updated = 0, 0
    for item in items:
        course = session.exec(
            select(Course).where(Course.name == item.course_name)
        ).first()
        if not course:
            course = Course(name=item.course_name, external_id=item.course_external_id)
            session.add(course)
            session.commit()
            session.refresh(course)

        task = session.exec(
            select(Task).where(Task.external_id == item.external_id)
        ).first()
        if task:
            task.title = item.title
            task.due_at = item.due_at
            task.notes = item.notes
            task.updated_at = datetime.utcnow()
            updated += 1
        else:
            task = Task(
                title=item.title,
                notes=item.notes,
                course_id=course.id,
                due_at=item.due_at,
                time_needed_min=item.time_needed_min,
                source=TaskSource.canvas,
                external_id=item.external_id,
            )
            created += 1
        session.add(task)
    session.commit()
    return {"created": created, "updated": updated}


# --------------------------------------------------------------------------- #
# Cushion
# --------------------------------------------------------------------------- #
cushion_router = APIRouter(prefix="/cushion", tags=["cushion"], dependencies=[Depends(require_api_key)])


@cushion_router.get("", summary="Real-time deadline feasibility (the Cushion)")
def get_cushion(session: Session = Depends(get_session)):
    tasks = session.exec(select(Task)).all()
    commitments = session.exec(select(Commitment)).all()
    events = session.exec(select(Event)).all()
    report = compute_cushion(tasks, commitments, events)
    return {
        "computed_at": report.computed_at,
        "feasible": report.feasible,
        "total_cushion_min": report.total_cushion_min,
        "total_cushion_human": f"{report.total_cushion_min // 60}h {report.total_cushion_min % 60}m",
        "at_risk_task_ids": [t.task_id for t in report.per_task if t.at_risk],
        "unscheduled_task_ids": report.unscheduled_task_ids,
        "per_task": [t.__dict__ for t in report.per_task],
    }


@cushion_router.get("/availability", summary="Free study minutes per day (next N days)")
def get_availability(days: int = 7, session: Session = Depends(get_session)):
    commitments = session.exec(select(Commitment)).all()
    events = session.exec(select(Event)).all()
    return availability_days(commitments, events, days=max(1, min(days, 60)))


# --------------------------------------------------------------------------- #
# Commitments — weekly busy blocks (the UI manages these directly)
# --------------------------------------------------------------------------- #
commitments_router = APIRouter(
    prefix="/commitments", tags=["commitments"], dependencies=[Depends(require_api_key)]
)


@commitments_router.get("", summary="List weekly commitments")
def list_commitments(session: Session = Depends(get_session)):
    return session.exec(select(Commitment)).all()


@commitments_router.post("", status_code=201, summary="Add a weekly commitment")
def create_commitment(c: Commitment, session: Session = Depends(get_session)):
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@commitments_router.delete("/{cid}", status_code=204, summary="Delete a commitment")
def delete_commitment(cid: int, session: Session = Depends(get_session)):
    c = session.get(Commitment, cid)
    if c:
        session.delete(c)
        session.commit()
