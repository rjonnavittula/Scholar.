"""Unit tests for the Cushion engine — pure stdlib, no DB needed.

Run:  python3 -m tests.test_cushion   (from repo root)
  or: python3 -m unittest tests.test_cushion -v
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import datetime, time

from app.cushion import busy_minutes_by_day, compute_cushion, free_minutes_between


# ---- duck-typed stand-ins for the SQLModel classes ------------------------- #
@dataclass
class FakeTask:
    id: int
    title: str
    due_at: datetime | None
    time_needed_min: int = 0
    time_spent_min: int = 0
    priority: int = 0
    status: str = "todo"

    @property
    def remaining_min(self) -> int:
        if self.status == "done":
            return 0
        return max(0, self.time_needed_min - self.time_spent_min)


@dataclass
class FakeCommitment:
    title: str
    weekday: int
    start: time
    end: time


@dataclass
class FakeEvent:
    title: str
    start_at: datetime
    end_at: datetime


# Fixed clock: Monday 2026-06-08 09:00 UTC. Flat 240 min/day capacity.
NOW = datetime(2026, 6, 8, 9, 0)
CAP = {d: 240 for d in range(7)}


class CushionTests(unittest.TestCase):
    def test_feasible_simple(self):
        # 180 min due Friday; Mon..Fri = 5 days * 240 = 1200 free.
        t = FakeTask(1, "HW3", datetime(2026, 6, 12, 23, 59), time_needed_min=180)
        r = compute_cushion([t], [], [], now=NOW, capacity=CAP)
        self.assertTrue(r.feasible)
        self.assertEqual(r.total_cushion_min, 1200 - 180)
        self.assertEqual(r.per_task[0].slack_min, 1020)

    def test_infeasible_flags_at_risk(self):
        # 600 min due tomorrow; only Mon+Tue = 480 free → slack -120.
        t = FakeTask(1, "Cram", datetime(2026, 6, 9, 23, 59), time_needed_min=600)
        r = compute_cushion([t], [], [], now=NOW, capacity=CAP)
        self.assertFalse(r.feasible)
        self.assertEqual(r.total_cushion_min, -120)
        self.assertTrue(r.per_task[0].at_risk)

    def test_cumulative_edf_ordering(self):
        # Task A due Tue (200), Task B due Wed (200).
        # By Tue: free 480, need 200 → slack 280.
        # By Wed: free 720, need 400 → slack 320. Tightest = 280.
        a = FakeTask(1, "A", datetime(2026, 6, 9, 23, 59), time_needed_min=200)
        b = FakeTask(2, "B", datetime(2026, 6, 10, 23, 59), time_needed_min=200)
        r = compute_cushion([b, a], [], [], now=NOW, capacity=CAP)  # unsorted input
        self.assertEqual([t.task_id for t in r.per_task], [1, 2])    # EDF sorted
        self.assertEqual(r.per_task[0].slack_min, 280)
        self.assertEqual(r.per_task[1].slack_min, 320)
        self.assertEqual(r.total_cushion_min, 280)

    def test_commitments_reduce_free_time(self):
        # 2h lecture every weekday → capacity effectively 120/day.
        lec = [FakeCommitment("Lecture", wd, time(10, 0), time(12, 0)) for wd in range(5)]
        t = FakeTask(1, "HW", datetime(2026, 6, 12, 23, 59), time_needed_min=180)
        r = compute_cushion([t], lec, [], now=NOW, capacity=CAP)
        self.assertEqual(r.total_cushion_min, 5 * 120 - 180)  # 420

    def test_event_blocks_one_day(self):
        # A 4h event Tuesday wipes out that whole day's 240-min capacity
        # (free is clamped at 0, never negative).
        ev = FakeEvent("Trip", datetime(2026, 6, 9, 8, 0), datetime(2026, 6, 9, 12, 0))
        t = FakeTask(1, "HW", datetime(2026, 6, 10, 23, 59), time_needed_min=100)
        r = compute_cushion([t], [], [ev], now=NOW, capacity=CAP)
        self.assertEqual(r.per_task[0].free_until_due_min, 240 + 0 + 240)
        self.assertEqual(r.total_cushion_min, 380)

    def test_done_and_progress_excluded(self):
        done = FakeTask(1, "Done", datetime(2026, 6, 9, 23, 59), 300, status="done")
        partial = FakeTask(2, "Half", datetime(2026, 6, 9, 23, 59), 200, time_spent_min=150)
        r = compute_cushion([done, partial], [], [], now=NOW, capacity=CAP)
        self.assertEqual(len(r.per_task), 1)            # done task dropped
        self.assertEqual(r.per_task[0].remaining_min, 50)  # progress counted

    def test_no_due_date_reported_unscheduled(self):
        t = FakeTask(7, "Someday", None, time_needed_min=60)
        r = compute_cushion([t], [], [], now=NOW, capacity=CAP)
        self.assertEqual(r.per_task, [])
        self.assertEqual(r.unscheduled_task_ids, [7])
        self.assertTrue(r.feasible)

    def test_helpers_directly(self):
        busy = busy_minutes_by_day(
            [FakeCommitment("x", 0, time(9, 0), time(10, 30))], [],
            NOW.date(), NOW.date(),
        )
        self.assertEqual(busy[NOW.date()], 90)
        free = free_minutes_between(NOW, datetime(2026, 6, 8, 23, 0), busy, CAP)
        self.assertEqual(free, 150)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class AvailabilityTests(unittest.TestCase):
    def test_seven_day_window(self):
        from app.cushion import availability_days
        lec = [FakeCommitment("L", 0, time(10, 0), time(12, 0))]  # Mondays −120
        days = availability_days(lec, [], now=NOW, days=7, capacity=CAP)
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]["date"], "2026-06-08")        # Monday
        self.assertEqual(days[0]["free_min"], 120)             # 240 − 120
        self.assertEqual(days[1]["free_min"], 240)             # Tuesday untouched
        self.assertEqual(sum(d["capacity_min"] for d in days), 7 * 240)

    def test_busy_clamped_to_capacity(self):
        from app.cushion import availability_days
        ev = FakeEvent("AllDay", datetime(2026, 6, 9, 0, 0), datetime(2026, 6, 9, 23, 0))
        days = availability_days([], [ev], now=NOW, days=2, capacity=CAP)
        self.assertEqual(days[1]["busy_min"], 240)   # clamped, not 1380
        self.assertEqual(days[1]["free_min"], 0)
