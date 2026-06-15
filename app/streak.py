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
