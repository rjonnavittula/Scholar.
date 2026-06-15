"""The engine (timezone-aware): availability from awake windows, and the Cushion.

Everything reconciles in UTC underneath; wall-clock inputs are interpreted in
named IANA zones so DST is handled by the tz database automatically.

- Awake windows + planned study blocks live in the user's HOME zone (they
  follow the body: change home_tz and the whole week re-renders).
- Activities each carry their OWN zone (a physical ET lecture stays ET even
  when the user is in PT; a local workout uses home_tz). Default = home_tz.
- Due dates are stored as UTC instants (anchored in school_tz at entry).

Pure stdlib (zoneinfo); duck-typed inputs so it unit-tests without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Sequence
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.models import Activity, Holiday, PlannedBlock, Task, Term

DAY_MIN = 1440
UTC = ZoneInfo("UTC")


def zone(name: str | None, fallback: str) -> ZoneInfo:
    try:
        return ZoneInfo(name) if name else ZoneInfo(fallback)
    except Exception:
        return ZoneInfo(fallback)


def merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in sorted(i for i in intervals if i[1] > i[0]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract(window: tuple[int, int], busy: list[tuple[int, int]]) -> list[tuple[int, int]]:
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


def wall_to_utc(local_date: date, minutes: int, tz: ZoneInfo) -> datetime:
    naive = datetime.combine(local_date, time()) + timedelta(minutes=minutes)
    return naive.replace(tzinfo=tz).astimezone(UTC)


def utc_to_wall_min(instant: datetime, local_date: date, tz: ZoneInfo) -> int | None:
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    local = instant.astimezone(tz)
    if local.date() < local_date:
        return 0
    if local.date() > local_date:
        return DAY_MIN
    return local.hour * 60 + local.minute


@dataclass
class EngineConfig:
    min_block_min: int = 30
    home_tz: str = "America/New_York"
    school_tz: str = "America/New_York"
    awake: dict = field(default=None)  # weekday -> (start,end) home wall minutes

    def window(self, weekday: int) -> tuple[int, int]:
        if self.awake and weekday in self.awake:
            return self.awake[weekday]
        return (480, 1410)


def _activity_busy_for_day(local_date: date, home: ZoneInfo, activities) -> list[tuple[int, int]]:
    busy: list[tuple[int, int]] = []
    for a in activities:
        atz = zone(getattr(a, "tz", None), home.key)
        for delta in (-1, 0, 1):
            cand = local_date + timedelta(days=delta)
            if cand.weekday() != a.weekday:
                continue
            s_utc = wall_to_utc(cand, a.start_min, atz)
            e_utc = wall_to_utc(cand, a.end_min, atz)
            sm = utc_to_wall_min(s_utc, local_date, home)
            em = utc_to_wall_min(e_utc, local_date, home)
            if sm is None or em is None or em <= sm:
                continue
            busy.append((sm, em))
    return busy


def _planned_busy_for_day(local_date: date, home: ZoneInfo, planned) -> list[tuple[int, int]]:
    busy = []
    for p in planned:
        s = p.start_at if p.start_at.tzinfo else p.start_at.replace(tzinfo=UTC)
        e = p.end_at if p.end_at.tzinfo else p.end_at.replace(tzinfo=UTC)
        sm = utc_to_wall_min(s, local_date, home)
        em = utc_to_wall_min(e, local_date, home)
        if sm is None or em is None or em <= sm:
            continue
        busy.append((sm, em))
    return busy


def in_term(d: date, term, holidays) -> bool:
    if any(h.day == d for h in holidays):
        return False
    if term:
        if term.classes_start and d < term.classes_start:
            return False
        end = term.exam_end or term.classes_end
        if end and d > end:
            return False
    return True


def day_free_gaps_utc(local_date, cfg, activities, planned, term=None, holidays=(), now=None):
    home = zone(cfg.home_tz, "America/New_York")
    now = now or datetime.now(UTC)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    now_home = now.astimezone(home).date()
    if local_date < now_home or not in_term(local_date, term, holidays):
        return []
    lo, hi = cfg.window(local_date.weekday())
    if local_date == now_home:
        now_min = now.astimezone(home).hour * 60 + now.astimezone(home).minute
        lo = max(lo, now_min)
    if hi <= lo:
        return []
    busy = merge(_activity_busy_for_day(local_date, home, activities)
                 + _planned_busy_for_day(local_date, home, planned))
    gaps_min = [(s, e) for s, e in subtract((lo, hi), busy) if e - s >= cfg.min_block_min]
    return [(wall_to_utc(local_date, s, home), wall_to_utc(local_date, e, home))
            for s, e in gaps_min]


def day_free_minutes(local_date, cfg, activities, planned, term=None, holidays=(), now=None) -> int:
    return sum(int((e - s).total_seconds() // 60)
               for s, e in day_free_gaps_utc(local_date, cfg, activities, planned, term, holidays, now))


def free_minutes_until(due, cfg, activities, planned, term=None, holidays=(), now=None) -> int:
    home = zone(cfg.home_tz, "America/New_York")
    now = now or datetime.now(UTC)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    due = due if due.tzinfo else due.replace(tzinfo=UTC)
    if due <= now:
        return 0
    total = 0
    d = now.astimezone(home).date()
    last = due.astimezone(home).date()
    while d <= last:
        for s, e in day_free_gaps_utc(d, cfg, activities, planned, term, holidays, now):
            s2, e2 = max(s, now), min(e, due)
            if e2 > s2:
                total += int((e2 - s2).total_seconds() // 60)
        d += timedelta(days=1)
    return total


def availability_days(start, days, cfg, activities, planned, term=None, holidays=(), now=None):
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
    per_task: list
    unscheduled_task_ids: list


def compute_cushion(tasks, cfg, activities, planned, term=None, holidays=(), now=None):
    now = now or datetime.now(UTC)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    open_tasks = [t for t in tasks if t.remaining_min > 0]
    scheduled = sorted(
        (t for t in open_tasks if t.due_at),
        key=lambda t: ((t.due_at if t.due_at.tzinfo else t.due_at.replace(tzinfo=UTC)),
                       -int(t.priority_flag)))
    unscheduled = [t.id for t in open_tasks if not t.due_at]
    per = []
    cum = 0
    tightest = None
    for t in scheduled:
        cum += t.remaining_min
        free = free_minutes_until(t.due_at, cfg, activities, planned, term, holidays, now)
        cushion = free - cum
        tightest = cushion if tightest is None else min(tightest, cushion)
        per.append(TaskCushion(t.id, t.title, t.due_at, t.remaining_min, free, cum, cushion))
    return CushionReport(now, tightest if tightest is not None else 0,
                         (tightest is None or tightest >= 0), per, unscheduled)
