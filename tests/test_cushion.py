"""Engine tests — pure stdlib. python3 -m unittest tests.test_cushion -v"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import date, datetime

from app.cushion import (
    EngineConfig, availability_days, compute_cushion, day_free_gaps,
    day_free_minutes, free_minutes_until, merge, subtract,
)


@dataclass
class A:  # activity
    weekday: int
    start_min: int
    end_min: int


@dataclass
class P:  # planned block
    start_at: datetime
    end_at: datetime


@dataclass
class T:  # task
    id: int
    title: str
    due_at: datetime | None
    time_needed_min: int = 60
    time_spent_min: int = 0
    priority_flag: bool = False
    status: str = "todo"

    @property
    def remaining_min(self):
        return 0 if self.status == "done" else max(0, self.time_needed_min - self.time_spent_min)


@dataclass
class Trm:
    classes_start: date | None = None
    classes_end: date | None = None
    exam_end: date | None = None


@dataclass
class H:
    day: date
    name: str = ""


# Monday 2026-06-08, 09:00. Awake 08:00–22:00 daily (840 min).
NOW = datetime(2026, 6, 8, 9, 0)
CFG = EngineConfig(min_block_min=30, awake={d: (480, 1320) for d in range(7)})
MON, TUE = date(2026, 6, 8), date(2026, 6, 9)


class Intervals(unittest.TestCase):
    def test_merge_and_subtract(self):
        self.assertEqual(merge([(600, 660), (650, 700), (60, 70)]), [(60, 70), (600, 700)])
        self.assertEqual(subtract((480, 1320), [(600, 700)]), [(480, 600), (700, 1320)])
        self.assertEqual(subtract((480, 1320), [(400, 1400)]), [])


class Availability(unittest.TestCase):
    def test_plain_day_from_now(self):
        # today: awake clipped to 09:00 → 540..1320 = 780
        self.assertEqual(day_free_minutes(MON, CFG, [], [], now=NOW), 780)
        # tomorrow: full window 840
        self.assertEqual(day_free_minutes(TUE, CFG, [], [], now=NOW), 840)

    def test_activity_consumes(self):
        lec = [A(1, 600, 720)]  # Tue 10:00–12:00
        self.assertEqual(day_free_minutes(TUE, CFG, lec, [], now=NOW), 840 - 120)

    def test_min_block_drops_slivers(self):
        # two activities leaving a 20-min gap between them: gap discarded
        acts = [A(1, 480, 700), A(1, 720, 1320)]
        self.assertEqual(day_free_minutes(TUE, CFG, acts, [], now=NOW), 0)
        gaps = day_free_gaps(TUE, CFG, [A(1, 480, 700), A(1, 740, 1320)], [], now=NOW)
        self.assertEqual(gaps, [(700, 740)])  # 40 min survives

    def test_planned_block_consumes(self):
        pb = [P(datetime(2026, 6, 9, 18, 0), datetime(2026, 6, 9, 20, 0))]
        self.assertEqual(day_free_minutes(TUE, CFG, [], pb, now=NOW), 840 - 120)

    def test_term_and_holiday(self):
        term = Trm(classes_start=date(2026, 6, 10))
        self.assertEqual(day_free_minutes(TUE, CFG, [], [], term=term, now=NOW), 0)
        hol = [H(TUE)]
        self.assertEqual(day_free_minutes(TUE, CFG, [], [], holidays=hol, now=NOW), 0)

    def test_past_day_zero(self):
        self.assertEqual(day_free_minutes(date(2026, 6, 7), CFG, [], [], now=NOW), 0)

    def test_due_time_clips(self):
        due = datetime(2026, 6, 9, 12, 0)
        # Mon 09:00→22:00 = 780, Tue 08:00→12:00 = 240
        self.assertEqual(free_minutes_until(due, CFG, [], [], now=NOW), 1020)

    def test_availability_shape(self):
        days = availability_days(MON, 7, CFG, [], [], now=NOW)
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]["free_min"], 780)
        self.assertEqual(days[1]["awake"], (480, 1320))
        self.assertTrue(all(d["in_term"] for d in days))


class Cushion(unittest.TestCase):
    def test_edf_cumulative(self):
        t1 = T(1, "A", datetime(2026, 6, 8, 22, 0), 200)   # free till then: 780
        t2 = T(2, "B", datetime(2026, 6, 9, 22, 0), 200)   # free: 780+840=1620
        r = compute_cushion([t2, t1], CFG, [], [], now=NOW)
        self.assertEqual([c.task_id for c in r.per_task], [1, 2])
        self.assertEqual(r.per_task[0].cushion_min, 780 - 200)
        self.assertEqual(r.per_task[1].cushion_min, 1620 - 400)
        self.assertEqual(r.total_cushion_min, 580)
        self.assertTrue(r.feasible)

    def test_infeasible(self):
        t = T(1, "Cram", datetime(2026, 6, 8, 12, 0), 600)  # free 09→12 = 180
        r = compute_cushion([t], CFG, [], [], now=NOW)
        self.assertEqual(r.per_task[0].cushion_min, 180 - 600)
        self.assertFalse(r.feasible)

    def test_levels(self):
        t = T(1, "x", datetime(2026, 6, 8, 22, 0), 700)  # cushion 80, 40% of 700=280
        r = compute_cushion([t], CFG, [], [], now=NOW)
        self.assertEqual(r.per_task[0].level(40), "yellow")
        self.assertEqual(r.per_task[0].level(5), "green")

    def test_done_and_progress(self):
        done = T(1, "d", datetime(2026, 6, 9, 22, 0), 300, status="done")
        half = T(2, "h", datetime(2026, 6, 9, 22, 0), 200, time_spent_min=150)
        r = compute_cushion([done, half], CFG, [], [], now=NOW)
        self.assertEqual(len(r.per_task), 1)
        self.assertEqual(r.per_task[0].remaining_min, 50)

    def test_unscheduled(self):
        r = compute_cushion([T(9, "someday", None, 60)], CFG, [], [], now=NOW)
        self.assertEqual(r.unscheduled_task_ids, [9])
        self.assertTrue(r.feasible)

    def test_planned_blocks_reduce_cushion(self):
        # planning 2h tomorrow doesn't change total free-vs-needed for tasks
        # due AFTER the block... but blocks consume availability:
        pb = [P(datetime(2026, 6, 9, 8, 0), datetime(2026, 6, 9, 10, 0))]
        t = T(1, "A", datetime(2026, 6, 9, 22, 0), 200)
        r = compute_cushion([t], CFG, [], pb, now=NOW)
        self.assertEqual(r.per_task[0].free_until_due_min, 780 + 840 - 120)


if __name__ == "__main__":
    unittest.main(verbosity=2)
