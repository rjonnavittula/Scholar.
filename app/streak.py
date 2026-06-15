"""Study Streak — a daily efficiency score (0..100) per calendar day.

v4a keeps the formula honest and simple (no estimate-accuracy grading yet —
that needs history and lands with the calibration engine):

  throughput  : tasks completed that day        -> rewards getting things done
  effort      : focused minutes logged that day -> rewards real work
  overdue_pen : tasks overdue as of that day     -> STACKS; each one dims more

  score = clamp( base(throughput, effort) - overdue_pen , 0, 100 )

Intensity tiers for the dots: 0 empty, 1 faint, 2 mid, 3 full.

Pure stdlib; duck-typed inputs so it unit-tests without a database. All
datetimes are UTC instants; the "day" is computed in the user's home zone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")


def _zone(name, fallback="America/New_York"):
    try:
        return ZoneInfo(name) if name else ZoneInfo(fallback)
    except Exception:
        return ZoneInfo(fallback)


def _day_in_zone(instant: datetime, tz: ZoneInfo) -> date:
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(tz).date()


@dataclass
class DayScore:
    day: date
    completed: int
    minutes: int
    overdue: int
    score: int

    @property
    def level(self) -> int:
        if self.score <= 0:
            return 0
        if self.score < 34:
            return 1
        if self.score < 67:
            return 2
        return 3


def day_score(
    target: date, tasks, time_logs, home_tz: str = "America/New_York", now: datetime | None = None,
) -> DayScore:
    home = _zone(home_tz)
    now = now or datetime.now(UTC)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)

    completed = sum(
        1 for t in tasks
        if t.completed_at and _day_in_zone(t.completed_at, home) == target
    )
    minutes = sum(
        lg.minutes for lg in time_logs
        if _day_in_zone(lg.logged_at, home) == target
    )

    # Overdue as of end of `target`: due before the day's end, still not done
    # (or completed after it was due). Stacks: each overdue subtracts.
    day_end = datetime.combine(target + timedelta(days=1), datetime.min.time(), home).astimezone(UTC)
    overdue = 0
    for t in tasks:
        if not t.due_at:
            continue
        due = t.due_at if t.due_at.tzinfo else t.due_at.replace(tzinfo=UTC)
        if due >= day_end:
            continue  # not due yet by this day
        done = t.completed_at and (t.completed_at if t.completed_at.tzinfo
                                   else t.completed_at.replace(tzinfo=UTC))
        if not done or done > due:
            overdue += 1

    # base: throughput saturates around 4 tasks; effort around 4h.
    base = min(60, completed * 18) + min(40, minutes // 6)  # 240min -> 40
    pen = overdue * 22                                       # stacking
    score = max(0, min(100, base - pen))
    return DayScore(target, completed, minutes, overdue, score)


def streak_window(
    tasks, time_logs, days: int = 9, home_tz: str = "America/New_York", now: datetime | None = None,
) -> list[DayScore]:
    """Scores for the last `days` days, oldest first (for the dot bar)."""
    home = _zone(home_tz)
    now = now or datetime.now(UTC)
    today = _day_in_zone(now, home)
    out = []
    for i in range(days - 1, -1, -1):
        out.append(day_score(today - timedelta(days=i), tasks, time_logs, home_tz, now))
    return out


def current_streak(scores: list[DayScore]) -> int:
    """Consecutive days up to today with score > 0."""
    n = 0
    for sc in reversed(scores):
        if sc.score > 0:
            n += 1
        else:
            break
    return n


# --- v5d: richer stats for the Streak page (plan-adherence + rest days) ------

from collections import defaultdict  # noqa: E402


def _bucket(mins: int) -> int:
    """0 / <1h / 1-2h / 2-4h / 4h+  ->  0..4 (heatmap intensity)."""
    if mins <= 0:
        return 0
    if mins < 60:
        return 1
    if mins < 120:
        return 2
    if mins < 240:
        return 3
    return 4


def streak_stats(tasks, time_logs, planned, term_start: date | None = None,
                 home_tz: str = "America/New_York", now: datetime | None = None) -> dict:
    """Per-day used/planned grid + streak. A day keeps the streak if it's a
    REST day (nothing was planned) or you met at least half your planned time.
    Today never breaks the streak while it's still in progress."""
    home = _zone(home_tz)
    now = now or datetime.now(UTC)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    today = _day_in_zone(now, home)

    used: dict = defaultdict(int)
    for lg in time_logs:
        used[_day_in_zone(lg.logged_at, home)] += lg.minutes
    plan: dict = defaultdict(int)
    for b in planned:
        s = b.start_at if b.start_at.tzinfo else b.start_at.replace(tzinfo=UTC)
        e = b.end_at if b.end_at.tzinfo else b.end_at.replace(tzinfo=UTC)
        plan[_day_in_zone(s, home)] += max(0, int((e - s).total_seconds() // 60))

    start = term_start or (today - timedelta(days=120))
    if (today - start).days > 200:
        start = today - timedelta(days=200)
    end = max([today] + list(plan.keys()))

    cells = []
    d = start
    while d <= end:
        u, p = used.get(d, 0), plan.get(d, 0)
        rest = p == 0
        met = rest or (u >= max(1, round(p * 0.5)))
        cells.append({"day": d.isoformat(), "used": u, "planned": p, "rest": rest,
                      "met": met, "level": _bucket(u), "plevel": _bucket(p),
                      "future": d > today})
        d += timedelta(days=1)

    past = [c for c in cells if c["day"] <= today.isoformat()]
    # trailing run of met days (today pending doesn't break it)
    run = []
    for c in reversed(past):
        if c["day"] == today.isoformat() and c["used"] == 0 and c["planned"] > 0:
            continue
        if c["met"]:
            run.append(c)          # today-first order
        else:
            break
    sidx = [i for i, c in enumerate(run) if c["used"] > 0]
    cur = (max(sidx) + 1) if sidx else 0   # span back to the oldest STUDIED day; drop leading rest

    # longest: within each maximal met-run, the span between first & last study day
    longest = 0
    cur_run, runs = [], []
    for c in past:
        if c["met"]:
            cur_run.append(c)
        elif cur_run:
            runs.append(cur_run); cur_run = []
    if cur_run:
        runs.append(cur_run)
    for r in runs:
        s = [i for i, c in enumerate(r) if c["used"] > 0]
        if s:
            longest = max(longest, s[-1] - s[0] + 1)

    def rng(a, b):
        return sum(used.get(a + timedelta(days=i), 0) for i in range((b - a).days + 1))

    monday = today - timedelta(days=today.weekday())
    today_min, yest = used.get(today, 0), used.get(today - timedelta(days=1), 0)
    week, last_week = rng(monday, today), rng(monday - timedelta(days=7), monday - timedelta(days=1))
    term_min = sum(used.get(date.fromisoformat(c["day"]), 0) for c in past)

    def delta(c, p):
        if p == 0:
            return None
        return round((c - p) / p * 100)

    return {
        "current": cur, "longest": longest,
        "today_min": today_min, "yesterday_min": yest, "today_delta": delta(today_min, yest),
        "week_min": week, "last_week_min": last_week, "week_delta": delta(week, last_week),
        "term_min": term_min,
        "cells": cells,
        "today": today.isoformat(),
    }
