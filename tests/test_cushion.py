"""Engine unit tests — interval helpers + cushion math (pure stdlib).

Timezone/DST behaviour lives in test_timezone.py. This file covers the
zone-agnostic primitives and the EDF cushion logic.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.cushion import (EngineConfig, compute_cushion, day_free_minutes,
                         merge, subtract)

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")


@dataclass
class A:
    title: str; weekday: int; start_min: int; end_min: int
    color: str = "#5F6B5A"; tz: Optional[str] = None


@dataclass
class T:
    id: int; title: str; due_at: Optional[datetime]
    time_needed_min: int = 120; time_spent_min: int = 0
    priority_flag: bool = False; status: str = "todo"
    @property
    def remaining_min(self):
        return 0 if self.status == "done" else max(0, self.time_needed_min - self.time_spent_min)


# Fixed clock: Mon 2026-06-08 09:00 ET. Flat 8am-11pm awake window.
CFG = EngineConfig(min_block_min=30, home_tz="America/New_York",
                   school_tz="America/New_York", awake={i: (480, 1380) for i in range(7)})
NOW = datetime(2026, 6, 8, 9, 0, tzinfo=ET).astimezone(UTC)
DUE = lambda dn, h=23, m=59: datetime(2026, 6, dn, h, m, tzinfo=ET).astimezone(UTC)


class HelperTests(unittest.TestCase):
    def test_merge(self):
        self.assertEqual(merge([(60, 120), (100, 180), (300, 360)]), [(60, 180), (300, 360)])

    def test_subtract(self):
        self.assertEqual(subtract((480, 1380), [(600, 660)]), [(480, 600), (660, 1380)])

    def test_min_block_drops_slivers(self):
        # an activity leaving only a 20-min gap (< min_block 30) yields nothing there
        a = A("x", 0, 500, 1360)  # 8:20-22:40, leaves <30 either side of the 8-23 window
        fm = day_free_minutes(datetime(2026, 6, 8).date(), CFG, [a], [], None, (), NOW)
        # window 9:00(now)-23:00 minus 8:20-22:40 busy => 22:40-23:00 = 20min < 30 -> 0
        self.assertEqual(fm, 0)


class CushionTests(unittest.TestCase):
    def test_feasible_simple(self):
        r = compute_cushion([T(1, "HW", DUE(12), 180)], CFG, [], [], None, (), NOW)
        self.assertTrue(r.feasible)
        self.assertGreater(r.total_cushion_min, 0)

    def test_infeasible_flags(self):
        r = compute_cushion([T(1, "Cram", DUE(8), 900)], CFG, [], [], None, (), NOW)
        self.assertFalse(r.feasible)
        self.assertLess(r.total_cushion_min, 0)

    def test_edf_cumulative(self):
        a = T(1, "A", DUE(9), 200)
        b = T(2, "B", DUE(10), 200)
        r = compute_cushion([b, a], CFG, [], [], None, (), NOW)
        self.assertEqual([c.task_id for c in r.per_task], [1, 2])  # EDF ordered

    def test_levels(self):
        r = compute_cushion([T(1, "HW", DUE(12), 180)], CFG, [], [], None, (), NOW)
        self.assertIn(r.per_task[0].level(40), ("green", "yellow", "red"))

    def test_done_and_progress(self):
        done = T(1, "done", DUE(9), 300, status="done")
        partial = T(2, "half", DUE(9), 200, time_spent_min=150)
        r = compute_cushion([done, partial], CFG, [], [], None, (), NOW)
        self.assertEqual(len(r.per_task), 1)
        self.assertEqual(r.per_task[0].remaining_min, 50)

    def test_unscheduled(self):
        r = compute_cushion([T(7, "someday", None, 60)], CFG, [], [], None, (), NOW)
        self.assertEqual(r.unscheduled_task_ids, [7])
        self.assertEqual(r.per_task, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
