"""The engine: availability from awake windows, and the Cushion.

free(day) = awake window
            − activities on that weekday
            − planned blocks on that date
            , keeping only gaps >= min_block
            , zero outside the term or on holidays or in the past
            , clipped to "from now" for today.

cushion(task) = free minutes from now until its due moment
                − cumulative remaining work of every task due on/before it
                (earliest-deadline-first feasibility).

Pure stdlib; duck-typed inputs so it unit-tests without a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Iterable, Sequence

if TYPE_CHECKING:
    from app.models import Activity, AwakeTime, Holiday, PlannedBlock, Task, Term

DAY_MIN = 1440


# --------------------------------------------------------------------------- #
# interval helpers (all minutes-since-midnight ints)
# --------------------------------------------------------------------------- #
def merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in sorted(i for i in intervals if i[1] > i[0]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract(window: tuple[int, int], busy: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Gaps of `window` not covered by `busy` (busy must be merged)."""
    gaps: list[tuple[int, int]] = []
    cur = window[0]
    for s, e in busy:
        if e <= window[0] or s >= window[1]:
            continue
        if s > cur:
            gaps.append((cur, min(s, window[1])))
        cur = max(cur, e)
    if cur < window[1]:
        gaps.append((cur, window[1]))
    return gaps


def _dt_to_min(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


# --------------------------------------------------------------------------- #
# availability
# --------------------------------------------------------------------------- #
@dataclass
class EngineConfig:
    min_block_min: int = 30
    awake: dict[int, tuple[int, int]] = None  # weekday -> (start,end)

    def window(self, weekday: int) -> tuple[int, int]:
        if self.awake and weekday in self.awake:
            return self.awake[weekday]
        return (480, 1410)


def day_busy(
    d: date,
    activities: Iterable["Activity"],
    planned: Iterable["PlannedBlock"],
) -> list[tuple[int, int]]:
    busy = [(a.start_min, a.end_min) for a in activities if a.weekday == d.weekday()]
    for p in planned:
        if p.start_at.date() <= d <= p.end_at.date():
            s = _dt_to_min(p.start_at) if p.start_at.date() == d else 0
            e = _dt_to_min(p.end_at) if p.end_at.date() == d else DAY_MIN
            busy.append((s, e))
    return merge(busy)


def in_term(d: date, term: "Term | None", holidays: Sequence["Holiday"]) -> bool:
    if any(h.day == d for h in holidays):
        return False
    if term:
        if term.classes_start and d < term.classes_start:
            return False
        end = term.exam_end or term.classes_end
        if end and d > end:
            return False
    return True


def day_free_gaps(
    d: date,
    cfg: EngineConfig,
    activities: Iterable["Activity"],
    planned: Iterable["PlannedBlock"],
    term: "Term | None" = None,
    holidays: Sequence["Holiday"] = (),
    now: datetime | None = None,
    until_min: int | None = None,
) -> list[tuple[int, int]]:
    """Usable study gaps for one day (each >= min_block)."""
    now = now or datetime.now()
    if d < now.date() or not in_term(d, term, holidays):
        return []
    lo, hi = cfg.window(d.weekday())
    if d == now.date():
        lo = max(lo, _dt_to_min(now))
    if until_min is not None:
        hi = min(hi, until_min)
    if hi <= lo:
        return []
    gaps = subtract((lo, hi), day_busy(d, activities, planned))
    return [(s, e) for s, e in gaps if e - s >= cfg.min_block_min]


def day_free_minutes(d, cfg, activities, planned, term=None, holidays=(), now=None,
                     until_min=None) -> int:
    return sum(e - s for s, e in day_free_gaps(
        d, cfg, activities, planned, term, holidays, now, until_min))


def free_minutes_until(
    due: datetime,
    cfg: EngineConfig,
    activities, planned, term=None, holidays=(), now: datetime | None = None,
) -> int:
    now = now or datetime.now()
    if due <= now:
        return 0
    total, d = 0, now.date()
    while d <= due.date():
        until = _dt_to_min(due) if d == due.date() else None
        total += day_free_minutes(d, cfg, activities, planned, term, holidays, now, until)
        d += timedelta(days=1)
    return total


def availability_days(
    start: date, days: int, cfg: EngineConfig,
    activities, planned, term=None, holidays=(), now: datetime | None = None,
) -> list[dict]:
    now = now or datetime.now()
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        out.append({
            "date": d.isoformat(),
            "free_min": day_free_minutes(d, cfg, activities, planned, term, holidays, now),
            "awake": cfg.window(d.weekday()),
            "in_term": in_term(d, term, holidays),
        })
    return out


# --------------------------------------------------------------------------- #
# cushion
# --------------------------------------------------------------------------- #
@dataclass
class TaskCushion:
    task_id: int
    title: str
    due_at: datetime
    remaining_min: int
    free_until_due_min: int
    cumulative_needed_min: int
    cushion_min: int

    def level(self, yellow_pct: int) -> str:
        if self.cushion_min < 0:
            return "red"
        if self.cushion_min <= self.remaining_min * yellow_pct / 100:
            return "yellow"
        return "green"


@dataclass
class CushionReport:
    computed_at: datetime
    total_cushion_min: int
    feasible: bool
    per_task: list[TaskCushion]
    unscheduled_task_ids: list[int]


def compute_cushion(
    tasks: Sequence["Task"], cfg: EngineConfig,
    activities, planned, term=None, holidays=(), now: datetime | None = None,
) -> CushionReport:
    now = now or datetime.now()
    open_tasks = [t for t in tasks if t.remaining_min > 0]
    scheduled = sorted((t for t in open_tasks if t.due_at),
                       key=lambda t: (t.due_at, -int(t.priority_flag)))
    unscheduled = [t.id for t in open_tasks if not t.due_at]

    per: list[TaskCushion] = []
    cum = 0
    tightest = None
    for t in scheduled:
        cum += t.remaining_min
        free = free_minutes_until(t.due_at, cfg, activities, planned, term, holidays, now)
        cushion = free - cum
        tightest = cushion if tightest is None else min(tightest, cushion)
        per.append(TaskCushion(t.id, t.title, t.due_at, t.remaining_min, free, cum, cushion))

    return CushionReport(
        computed_at=now,
        total_cushion_min=tightest if tightest is not None else 0,
        feasible=(tightest is None or tightest >= 0),
        per_task=per,
        unscheduled_task_ids=unscheduled,
    )
