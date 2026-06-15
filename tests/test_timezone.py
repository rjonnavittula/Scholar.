"""Timezone + DST correctness for the engine (pure stdlib)."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import Optional

from app.cushion import (EngineConfig, compute_cushion, day_free_minutes,
                         free_minutes_until, day_free_gaps_utc)

UTC = ZoneInfo("UTC"); PT = ZoneInfo("America/Los_Angeles"); ET = ZoneInfo("America/New_York")


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


class TimezoneTests(unittest.TestCase):
    def setUp(self):
        self.pt_home = EngineConfig(min_block_min=30, home_tz="America/Los_Angeles",
                                    school_tz="America/New_York", awake={i: (480, 1380) for i in range(7)})
        self.et_home = EngineConfig(min_block_min=30, home_tz="America/New_York",
                                    school_tz="America/New_York", awake={i: (480, 1380) for i in range(7)})

    def test_et_lecture_from_pt_consumes_pt_time(self):
        lec = A("CMPEN331", 2, 840, 890, tz="America/New_York")  # 2pm ET = 11am PT
        now = datetime(2026, 3, 4, 7, 0, tzinfo=PT).astimezone(UTC)
        no = day_free_minutes(datetime(2026, 3, 4).date(), self.pt_home, [], [], None, (), now)
        wi = day_free_minutes(datetime(2026, 3, 4).date(), self.pt_home, [lec], [], None, (), now)
        self.assertEqual(no - wi, 50)

    def test_dst_spring_forward_loses_hour(self):
        cfg = EngineConfig(min_block_min=30, home_tz="America/New_York",
                           school_tz="America/New_York", awake={6: (60, 300)})  # 1-5am Sun
        now = datetime(2026, 3, 7, 0, 0, tzinfo=ET).astimezone(UTC)
        gaps = day_free_gaps_utc(datetime(2026, 3, 8).date(), cfg, [], [], None, (), now)
        real = sum(int((e - s).total_seconds() // 60) for s, e in gaps)
        self.assertEqual(real, 180)  # 4h wall window crossing 2am gap = 3 real hours

    def test_dst_fall_back_gains_hour(self):
        cfg = EngineConfig(min_block_min=30, home_tz="America/New_York",
                           school_tz="America/New_York", awake={6: (60, 180)})  # 1-3am Sun
        now = datetime(2026, 10, 31, 0, 0, tzinfo=ET).astimezone(UTC)
        gaps = day_free_gaps_utc(datetime(2026, 11, 1).date(), cfg, [], [], None, (), now)
        real = sum(int((e - s).total_seconds() // 60) for s, e in gaps)
        self.assertEqual(real, 180)  # 2h wall window over repeated hour = 3 real hours

    def test_deadline_anchored_in_school_zone(self):
        now = datetime(2026, 3, 4, 12, 0, tzinfo=PT).astimezone(UTC)
        due = datetime(2026, 3, 4, 23, 59, tzinfo=ET).astimezone(UTC)  # 8:59pm PT
        fm = free_minutes_until(due, self.pt_home, [], [], None, (), now)
        self.assertTrue(500 < fm < 560)  # noon->8:59pm PT, not the full day

    def test_feasible_cushion_across_zones(self):
        now = datetime(2026, 3, 2, 9, 0, tzinfo=PT).astimezone(UTC)
        due = datetime(2026, 3, 6, 23, 59, tzinfo=ET).astimezone(UTC)
        r = compute_cushion([T(1, "HW", due, 180)], self.pt_home, [], [], None, (), now)
        self.assertTrue(r.feasible)
        self.assertGreater(r.total_cushion_min, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
