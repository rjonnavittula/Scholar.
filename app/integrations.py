"""Server-side Canvas sync: upserts courses + upcoming assignments."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models import Course, Settings, Source, Task
from app.ics import parse_ics, ext_id as ics_ext_id

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


# --- shared upsert helpers (used by token sync, ICS feed, and the bookmarklet) ---

def upsert_course(session: Session, name: str, canvas_id=None, seen: int = 1):
    ext = f"canvas:{canvas_id}" if canvas_id is not None else None
    course = None
    if ext:
        course = session.exec(select(Course).where(Course.external_id == ext)).first()
    if not course and name:
        course = session.exec(select(Course).where(Course.name == name)).first()
    if not course:
        course = Course(name=name or "course", source=Source.canvas, external_id=ext,
                        color=PALETTE[seen % len(PALETTE)])
        session.add(course); session.commit(); session.refresh(course)
    elif ext and not course.external_id:
        course.external_id = ext; course.source = Source.canvas; session.add(course)
    return course


def upsert_assignment(session: Session, st: Settings, *, ext_id: str, title: str,
                      due, course=None, url: str = "", category=None,
                      source: Source = Source.canvas) -> str:
    cat = category if category is not None else guess_category(title)
    task = session.exec(select(Task).where(Task.external_id == ext_id)).first()
    if task:
        task.title = title
        task.due_at = due
        if course and not task.course_id:
            task.course_id = course.id
        task.updated_at = datetime.now()
        session.add(task)
        return "updated"
    task = Task(
        title=title, course_id=(course.id if course else None), category=cat, due_at=due,
        start_date=(due.date() - timedelta(days=st.start_ahead_days)) if due else None,
        time_needed_min=ESTIMATES.get(cat, 60), notes=url or "",
        source=source, external_id=ext_id,
    )
    session.add(task)
    return "created"


# --- ICS calendar feed (no token, no cookie; server polls the feed URL) ---

def sync_canvas_ics(session: Session, st: Settings) -> dict:
    import urllib.request
    url = (st.canvas_ics_url or "").replace("webcal://", "https://")
    req = urllib.request.Request(url, headers={"User-Agent": "scholar/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        text = r.read().decode("utf-8", "replace")
    events = parse_ics(text)
    created = updated = 0
    for ev in events:
        title = ev.get("summary") or "assignment"
        due = ev.get("dtstart") or ev.get("dtend")
        res = upsert_assignment(session, st, ext_id=ics_ext_id(ev), title=title,
                                due=due, url=ev.get("url", ""))
        created += res == "created"
        updated += res == "updated"
    session.commit()
    return {"events": len(events), "created": created, "updated": updated}


# --- iCloud calendar (full CalDAV, Apple ID + app-specific password) -----------------

def sync_icloud(session: Session, st: Settings) -> dict:
    """Personal calendar events land as plain Tasks (category="Personal", not run
    through guess_category -- an event titled "Discussion with landlord" would
    otherwise mis-tag itself as coursework via that word alone), same reuse of
    upsert_assignment as every other source, just with source=Source.icloud so it's
    visually and structurally distinguishable from real coursework."""
    from app.icloud import fetch_events

    username = st.icloud_username or os.environ.get("HIVE_ICLOUD_USERNAME", "")
    password = st.icloud_password or os.environ.get("HIVE_ICLOUD_PASSWORD", "")
    if not username or not password:
        raise ValueError("icloud_not_configured")

    events = fetch_events(username, password, st.icloud_calendar_url or "")
    created = updated = 0
    for ev in events:
        res = upsert_assignment(
            session, st, ext_id=f"icloud:{ev['uid']}", title=ev["summary"] or "Event",
            due=ev["start"], category="Personal", source=Source.icloud,
        )
        created += res == "created"
        updated += res == "updated"
    session.commit()
    return {"events": len(events), "created": created, "updated": updated}


# --- bookmarklet payload import (data fetched in the browser on Canvas) ---

def import_canvas_payload(session: Session, st: Settings, payload: dict) -> dict:
    cmap = {}
    for i, c in enumerate(payload.get("courses", []) or []):
        course = upsert_course(session, c.get("name") or "", canvas_id=c.get("id"), seen=i + 1)
        if c.get("id") is not None:
            cmap[c["id"]] = course
    created = updated = 0
    for a in payload.get("assignments", []) or []:
        aid = a.get("id")
        if aid is None:
            continue
        due = None
        if a.get("due_at"):
            due = datetime.fromisoformat(str(a["due_at"]).replace("Z", "+00:00"))
        course = cmap.get(a.get("course_id"))
        res = upsert_assignment(session, st, ext_id=f"canvas:{aid}",
                                title=a.get("name") or "assignment", due=due,
                                course=course, url=a.get("html_url", "") or "")
        created += res == "created"
        updated += res == "updated"
    session.commit()
    return {"courses": len(cmap), "created": created, "updated": updated}


# --- syllabus import (reviewed candidate tasks from a PDF/text upload) ------

def import_syllabus_tasks(session: Session, st: Settings, *, course_name=None, items=None) -> dict:
    """Create plain tasks from a reviewed syllabus list. Optionally group them
    under a (new or existing) course. Due times land at 23:59 in the school zone."""
    from zoneinfo import ZoneInfo
    items = items or []
    course = None
    if course_name and course_name.strip():
        name = course_name.strip()
        course = session.exec(select(Course).where(Course.name == name)).first()
        if not course:
            idx = len(session.exec(select(Course)).all()) + 1
            course = Course(name=name, source=Source.manual, color=PALETTE[idx % len(PALETTE)])
            session.add(course); session.commit(); session.refresh(course)

    school_tz = (st.school_tz if st else None) or "America/New_York"
    try:
        tz = ZoneInfo(school_tz)
    except Exception:
        tz = ZoneInfo("America/New_York")
    ahead = (st.start_ahead_days if st else 3) or 3

    created = 0
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        due = None
        ds = it.get("due_date")
        if ds:
            try:
                local = datetime.fromisoformat(ds + "T23:59:00").replace(tzinfo=tz)
                due = local.astimezone(ZoneInfo("UTC"))
            except Exception:
                due = None
        cat = it.get("category") or guess_category(title)
        session.add(Task(
            title=title[:200], course_id=(course.id if course else None), category=cat,
            due_at=due, due_tz=school_tz if due else None,
            start_date=(due.date() - timedelta(days=ahead)) if due else None,
            time_needed_min=ESTIMATES.get(cat, 60), source=Source.manual,
        ))
        created += 1
    session.commit()
    return {"created": created, "course": course.name if course else None}
