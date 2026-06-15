"""Aggregations for the analytics page (Past view). Pulls from TimeLog,
PlannedBlock, Activity and the cushion's free-time model."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from app.analytics_util import RANGE_LABELS, range_bounds, recent_weeks, week_label
from app.cushion import day_free_minutes
from app.models import Course, PlannedBlock, Task, TimeLog


def _d(dt) -> date:
    return dt.date() if isinstance(dt, datetime) else dt


def past_analytics(session: Session, cfg, activities, planned, term, holidays,
                   range_key: str, today: date | None = None) -> dict:
    today = today or date.today()
    s, e = range_bounds(range_key, today)

    logs = session.exec(select(TimeLog)).all()
    tasks = {t.id: t for t in session.exec(select(Task)).all()}
    courses = {c.id: c for c in session.exec(select(Course)).all()}

    def in_range(d: date) -> bool:
        return (s is None or s <= d) and (e is None or d <= e)

    rlogs = [g for g in logs if in_range(_d(g.logged_at))]

    # effective window for day-based sums (bounded so 'all' doesn't loop forever)
    if s is None:
        ds = min((_d(g.logged_at) for g in logs), default=today - timedelta(days=6))
        win_s, win_e = max(ds, today - timedelta(days=59)), today
    else:
        win_s, win_e = s, e

    # time on tasks
    used_min = sum(g.minutes for g in rlogs)
    by_task_min: dict[int, int] = defaultdict(int)
    for g in rlogs:
        by_task_min[g.task_id] += g.minutes
    by_task = []
    for tid, m in sorted(by_task_min.items(), key=lambda kv: -kv[1]):
        t = tasks.get(tid)
        if not t:
            continue
        c = courses.get(t.course_id)
        by_task.append({"title": t.title, "minutes": m,
                        "course": c.name if c else None,
                        "color": (c.color if c else "#8A7F73")})
    by_course_min: dict[int, int] = defaultdict(int)
    for tid, m in by_task_min.items():
        t = tasks.get(tid)
        if t:
            by_course_min[t.course_id] += m
    by_course = [{"course": (courses.get(cid).name if courses.get(cid) else "unassigned"),
                  "color": (courses.get(cid).color if courses.get(cid) else "#8A7F73"),
                  "minutes": m}
                 for cid, m in sorted(by_course_min.items(), key=lambda kv: -kv[1])]
    most = by_task[0] if by_task else None

    # planned vs free vs activity over the window
    planned_min = 0
    for b in planned:
        if in_range(_d(b.start_at)):
            planned_min += max(0, int((b.end_at - b.start_at).total_seconds() // 60))
    free_min = 0
    activity_min = 0
    d = win_s
    guard = 0
    while d <= win_e and guard < 62:
        free_min += day_free_minutes(d, cfg, activities, planned, term, holidays)
        activity_min += sum(max(0, a.end_min - a.start_min)
                            for a in activities if a.weekday == d.weekday())
        d += timedelta(days=1)
        guard += 1

    study = {
        "used_min": used_min,
        "planned_not_used_min": max(0, planned_min - used_min),
        "free_min": free_min,
        "activity_min": activity_min,
    }

    # plan adherence per day (planned vs used), capped to ~31 days
    adherence = []
    ad_s = win_s if (win_e - win_s).days <= 31 else (win_e - timedelta(days=13))
    d = ad_s
    guard = 0
    while d <= win_e and guard < 32:
        p = sum(max(0, int((b.end_at - b.start_at).total_seconds() // 60))
                for b in planned if _d(b.start_at) == d)
        u = sum(g.minutes for g in logs if _d(g.logged_at) == d)
        adherence.append({"date": d.isoformat(),
                          "label": d.strftime("%b %d"),
                          "planned_min": p, "used_min": u})
        d += timedelta(days=1)
        guard += 1

    # time spent on tasks each week (always the recent 6 weeks)
    by_week = []
    for mon, label in recent_weeks(today, 6):
        wk_end = mon + timedelta(days=6)
        m = sum(g.minutes for g in logs if mon <= _d(g.logged_at) <= wk_end)
        by_week.append({"label": label, "minutes": m})

    return {
        "mode": "past",
        "range": {"key": range_key, "label": RANGE_LABELS.get(range_key, range_key),
                  "start": s.isoformat() if s else None,
                  "end": e.isoformat() if e else None},
        "study": study,
        "tasks_total_min": used_min,
        "most_consuming": most,
        "by_course": by_course,
        "by_task": by_task[:8],
        "plan_adherence": adherence,
        "by_week": by_week,
    }


def future_analytics(session: Session, cfg, activities, planned, term, holidays,
                     range_key: str, today: date | None = None) -> dict:
    from app.analytics_util import RANGE_LABELS, forward_weeks, range_bounds
    from app.rollup import roll_up

    today = today or date.today()
    s, e = range_bounds(range_key, today)
    win_s = max(today, s) if s else today
    win_e = e if e else today + timedelta(days=13)
    if win_e < win_s:
        win_e = win_s

    courses = {c.id: c for c in session.exec(select(Course)).all()}
    tasks = [t for t in roll_up(session.exec(select(Task)).all()) if t.parent_id is None]

    # available study time + activity + free over the window
    avail_min = activity_min = 0
    d, guard = win_s, 0
    while d <= win_e and guard < 120:
        avail_min += day_free_minutes(d, cfg, activities, planned, term, holidays)
        activity_min += sum(max(0, a.end_min - a.start_min)
                            for a in activities if a.weekday == d.weekday())
        d += timedelta(days=1); guard += 1

    planned_min = sum(max(0, int((b.end_at - b.start_at).total_seconds() // 60))
                      for b in planned if win_s <= _d(b.start_at) <= win_e)

    def due_in(t, a, b):
        return t.due_at and a <= _d(t.due_at) <= b and t.status != "done"

    due_tasks = [t for t in tasks if due_in(t, win_s, win_e)]
    workload_due = sum(t.remaining_min for t in due_tasks)
    by_course_min: dict = {}
    for t in due_tasks:
        by_course_min[t.course_id] = by_course_min.get(t.course_id, 0) + t.remaining_min
    wtot = sum(by_course_min.values()) or 1
    by_course = [{"course": (courses[cid].name if courses.get(cid) else "unassigned"),
                  "color": (courses[cid].color if courses.get(cid) else "#8A7F73"),
                  "minutes": m, "pct": round(m / wtot * 100)}
                 for cid, m in sorted(by_course_min.items(), key=lambda kv: -kv[1])]

    # workload + planned per upcoming week
    by_week = []
    for mon, label in forward_weeks(today, 10):
        wk_e = mon + timedelta(days=6)
        wl = sum(t.remaining_min for t in tasks if due_in(t, mon, wk_e))
        pl = sum(max(0, int((b.end_at - b.start_at).total_seconds() // 60))
                 for b in planned if mon <= _d(b.start_at) <= wk_e)
        by_week.append({"label": label, "workload_min": wl, "planned_min": pl})

    return {
        "mode": "future",
        "range": {"key": range_key, "label": RANGE_LABELS.get(range_key, range_key),
                  "start": win_s.isoformat(), "end": win_e.isoformat()},
        "cards": {
            "available_min": avail_min,
            "tasks_due": len(due_tasks),
            "workload_due_min": workload_due,
            "planned_min": planned_min,
            "left_to_plan_min": max(0, workload_due - planned_min),
        },
        "by_course": by_course,
        "breakdown": {"activity_min": activity_min, "planned_min": planned_min, "free_min": avail_min},
        "by_week": by_week,
    }
