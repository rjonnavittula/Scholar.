"""Server-side Canvas sync: upserts courses + upcoming assignments."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models import Course, Settings, Source, Task

PALETTE = ["#8A7F73", "#7A6A56", "#5F6B5A", "#6B5A66", "#56646E", "#7A5A4A"]

CATEGORY_HINTS = [
    ("exam", "Exam"), ("midterm", "Exam"), ("final", "Exam"),
    ("quiz", "Quiz"), ("lab", "Lab"), ("project", "Project"),
    ("discussion", "Discussion"), ("reading", "Reading"),
    ("homework", "Homework"), ("hw", "Homework"), ("assignment", "Homework"),
]

ESTIMATES = {"Exam": 240, "Project": 240, "Homework": 150, "Lab": 120,
             "Quiz": 60, "Discussion": 45, "Reading": 90, "": 60}


def guess_category(name: str) -> str:
    n = name.lower()
    for hint, cat in CATEGORY_HINTS:
        if hint in n:
            return cat
    return ""


def sync_canvas(session: Session, st: Settings) -> dict:
    from canvasapi import Canvas  # imported lazily; ships in the image

    canvas = Canvas(st.canvas_base_url, st.canvas_token)
    created = updated = 0
    courses_seen = 0

    for cc in canvas.get_courses(enrollment_state="active"):
        name = getattr(cc, "name", None)
        if not name:
            continue
        courses_seen += 1
        ext = f"canvas:{cc.id}"
        course = session.exec(select(Course).where(Course.external_id == ext)).first() \
            or session.exec(select(Course).where(Course.name == name)).first()
        if not course:
            course = Course(name=name, source=Source.canvas, external_id=ext,
                            color=PALETTE[courses_seen % len(PALETTE)])
            session.add(course); session.commit(); session.refresh(course)
        elif not course.external_id:
            course.external_id = ext
            course.source = Source.canvas
            session.add(course)

        for a in cc.get_assignments(bucket="upcoming"):
            text = f"canvas:{a.id}"
            due = None
            if getattr(a, "due_at", None):
                # Canvas returns UTC ISO; store naive local-ish (good enough v1)
                from zoneinfo import ZoneInfo
                due = datetime.fromisoformat(a.due_at.replace("Z", "+00:00")) \
                    .astimezone(ZoneInfo("UTC"))
            cat = guess_category(a.name)
            task = session.exec(select(Task).where(Task.external_id == text)).first()
            if task:
                task.title = a.name
                task.due_at = due
                task.updated_at = datetime.now()
                updated += 1
            else:
                task = Task(
                    title=a.name, course_id=course.id, category=cat, due_at=due,
                    start_date=(due.date() - timedelta(days=st.start_ahead_days)) if due else None,
                    time_needed_min=ESTIMATES.get(cat, 60),
                    notes=getattr(a, "html_url", "") or "",
                    source=Source.canvas, external_id=text,
                )
                created += 1
            session.add(task)
    session.commit()
    return {"courses": courses_seen, "created": created, "updated": updated}
