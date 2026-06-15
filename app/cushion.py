"""The Cushion engine.

This is the soul of the app and the one thing Super Productivity does not do.

Question it answers, continuously: *for every deadline, do I have enough free
study time between now and then to finish everything that is due by then?*

Algorithm (earliest-deadline-first feasibility scan):
  1. Build a map of free study minutes per calendar day:
        free(day) = capacity(weekday) - busy(day)
     where busy(day) = sum of commitment + event minutes landing on that day.
  2. Sort unfinished tasks by due date ascending.
  3. Walk the deadlines. For each task T (due D), the cumulative remaining work
     of every task due on/before D must fit inside the cumulative free study
     time available before D.
        slack(T) = free_minutes(now -> D) - sum(remaining for tasks due <= D)
  4. A negative slack anywhere means the schedule is infeasible: you will miss
     a deadline unless something changes. The overall Cushion is the *minimum*
     slack across all deadlines — your tightest point in the semester.

v0 simplifications (flagged for later refinement):
  - Days are counted whole; 'today' is not prorated by current time.
  - Tasks with no due date are excluded from the deadline scan but still
    reported in `unscheduled`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # pure-stdlib at runtime; only duck-typed attrs are used
    from app.models import Commitment, Event, Task

# Minutes of study you can realistically do on each weekday (0 = Mon).
# Sane default; expose as user config later.
DEFAULT_CAPACITY = {0: 240, 1: 240, 2: 240, 3: 240, 4: 180, 5: 300, 6: 300}


@dataclass
class TaskCushion:
    task_id: int
    title: str
    due_at: datetime
    remaining_min: int
    free_until_due_min: int
    cumulative_needed_min: int
    slack_min: int

    @property
    def at_risk(self) -> bool:
        return self.slack_min < 0


@dataclass
class CushionReport:
    computed_at: datetime
    total_cushion_min: int  # tightest slack across all deadlines
    feasible: bool
    per_task: list[TaskCushion]
    unscheduled_task_ids: list[int]


def _minutes(start, end) -> int:
    return max(0, int((datetime.combine(date.min, end) - datetime.combine(date.min, start)).total_seconds() // 60))


def busy_minutes_by_day(
    commitments: Iterable[Commitment],
    events: Iterable[Event],
    start: date,
    end: date,
) -> dict[date, int]:
    """Total blocked minutes per day from recurring commitments + one-off events."""
    busy: dict[date, int] = defaultdict(int)
    weekly: dict[int, int] = defaultdict(int)
    for c in commitments:
        weekly[c.weekday] += _minutes(c.start, c.end)

    d = start
    while d <= end:
        busy[d] += weekly.get(d.weekday(), 0)
        d += timedelta(days=1)

    for e in events:
        day = e.start_at.date()
        if start <= day <= end:
            busy[day] += max(0, int((e.end_at - e.start_at).total_seconds() // 60))
    return busy


def free_minutes_between(
    now: datetime,
    due: datetime,
    busy: dict[date, int],
    capacity: dict[int, int] = DEFAULT_CAPACITY,
) -> int:
    """Sum free study minutes from `now` up to `due`."""
    total = 0
    d = now.date()
    last = due.date()
    while d <= last:
        cap = capacity.get(d.weekday(), 0)
        total += max(0, cap - busy.get(d, 0))
        d += timedelta(days=1)
    return total


def availability_days(
    commitments: list[Commitment],
    events: list[Event],
    now: datetime | None = None,
    days: int = 7,
    capacity: dict[int, int] = DEFAULT_CAPACITY,
) -> list[dict]:
    """Per-day free study time for the next `days` days (the Shovel week bar)."""
    now = now or datetime.utcnow()
    end = (now + timedelta(days=days - 1)).date()
    busy = busy_minutes_by_day(commitments, events, now.date(), end)
    out: list[dict] = []
    d = now.date()
    while d <= end:
        cap = capacity.get(d.weekday(), 0)
        b = busy.get(d, 0)
        out.append(
            {
                "date": d.isoformat(),
                "capacity_min": cap,
                "busy_min": min(b, cap),
                "free_min": max(0, cap - b),
            }
        )
        d += timedelta(days=1)
    return out


def compute_cushion(
    tasks: list[Task],
    commitments: list[Commitment],
    events: list[Event],
    now: datetime | None = None,
    capacity: dict[int, int] = DEFAULT_CAPACITY,
    horizon_days: int = 120,
) -> CushionReport:
    now = now or datetime.utcnow()
    horizon = (now + timedelta(days=horizon_days)).date()
    busy = busy_minutes_by_day(commitments, events, now.date(), horizon)

    scheduled = [t for t in tasks if t.due_at and t.remaining_min > 0]
    scheduled.sort(key=lambda t: (t.due_at, -t.priority))
    unscheduled = [t.id for t in tasks if not t.due_at and t.remaining_min > 0]

    per_task: list[TaskCushion] = []
    cumulative_needed = 0
    tightest = None
    for t in scheduled:
        cumulative_needed += t.remaining_min
        free = free_minutes_between(now, t.due_at, busy, capacity)
        slack = free - cumulative_needed
        tightest = slack if tightest is None else min(tightest, slack)
        per_task.append(
            TaskCushion(
                task_id=t.id,
                title=t.title,
                due_at=t.due_at,
                remaining_min=t.remaining_min,
                free_until_due_min=free,
                cumulative_needed_min=cumulative_needed,
                slack_min=slack,
            )
        )

    return CushionReport(
        computed_at=now,
        total_cushion_min=tightest if tightest is not None else 0,
        feasible=(tightest is None or tightest >= 0),
        per_task=per_task,
        unscheduled_task_ids=unscheduled,
    )
