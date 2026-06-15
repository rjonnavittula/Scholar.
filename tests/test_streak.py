"""Study Streak engine tests (pure stdlib)."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import Optional

from app.streak import day_score, streak_window, current_streak

UTC = ZoneInfo("UTC"); ET = ZoneInfo("America/New_York")


@dataclass
class T:
    id: int
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class L:
    minutes: int
    logged_at: datetime


def et(y, m, d, h=12, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=ET).astimezone(UTC)


class StreakTests(unittest.TestCase):
    def test_empty_day_scores_zero(self):
        s = day_score(datetime(2026, 6, 8).date(), [], [], "America/New_York", et(2026, 6, 9))
        self.assertEqual(s.score, 0)
        self.assertEqual(s.level, 0)

    def test_completing_tasks_raises_score(self):
        day = datetime(2026, 6, 8).date()
        tasks = [T(1, completed_at=et(2026, 6, 8, 14)), T(2, completed_at=et(2026, 6, 8, 16))]
        s = day_score(day, tasks, [], "America/New_York", et(2026, 6, 9))
        self.assertEqual(s.completed, 2)
        self.assertGreater(s.score, 0)

    def test_logged_minutes_count_as_effort(self):
        day = datetime(2026, 6, 8).date()
        logs = [L(120, et(2026, 6, 8, 10)), L(120, et(2026, 6, 8, 15))]  # 240 min -> +40
        s = day_score(day, [], logs, "America/New_York", et(2026, 6, 9))
        self.assertEqual(s.minutes, 240)
        self.assertEqual(s.score, 40)

    def test_overdue_stacks_and_dims(self):
        day = datetime(2026, 6, 10).date()
        # two tasks due Jun 8 & 9, neither completed -> overdue by Jun 10
        tasks = [T(1, due_at=et(2026, 6, 8, 23, 59)), T(2, due_at=et(2026, 6, 9, 23, 59))]
        # also complete one task today for some base
        tasks.append(T(3, completed_at=et(2026, 6, 10, 12)))
        s = day_score(day, tasks, [], "America/New_York", et(2026, 6, 11))
        self.assertEqual(s.overdue, 2)
        # base = 18 (one completed) ; pen = 44 ; score floored at 0
        self.assertEqual(s.score, 0)

    def test_completed_on_time_not_overdue(self):
        day = datetime(2026, 6, 8).date()
        t = T(1, due_at=et(2026, 6, 8, 23, 59), completed_at=et(2026, 6, 8, 20))
        s = day_score(day, [t], [], "America/New_York", et(2026, 6, 9))
        self.assertEqual(s.overdue, 0)

    def test_window_and_streak(self):
        now = et(2026, 6, 10, 9)
        tasks = [T(1, completed_at=et(2026, 6, 8, 14)),
                 T(2, completed_at=et(2026, 6, 9, 14)),
                 T(3, completed_at=et(2026, 6, 10, 8))]
        w = streak_window(tasks, [], days=9, home_tz="America/New_York", now=now)
        self.assertEqual(len(w), 9)
        self.assertEqual(w[-1].day, datetime(2026, 6, 10).date())  # today last
        self.assertEqual(current_streak(w), 3)  # Jun 8,9,10 consecutive

    def test_levels_tiers(self):
        # craft scores across tiers
        from app.streak import DayScore
        from datetime import date as D
        self.assertEqual(DayScore(D(2026,6,8),0,0,0,0).level, 0)
        self.assertEqual(DayScore(D(2026,6,8),1,0,0,18).level, 1)
        self.assertEqual(DayScore(D(2026,6,8),2,120,0,56).level, 2)
        self.assertEqual(DayScore(D(2026,6,8),4,240,0,100).level, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
