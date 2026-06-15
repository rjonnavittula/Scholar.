import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from app.streak import streak_stats, _bucket

UTC = ZoneInfo("UTC")


class Log:
    def __init__(self, day, minutes):
        self.logged_at = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=12)
        self.minutes = minutes


class Block:
    def __init__(self, day, minutes):
        self.start_at = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=9)
        self.end_at = self.start_at + timedelta(minutes=minutes)


class StreakStatsTests(unittest.TestCase):
    TODAY = date(2026, 6, 14)
    NOW = datetime.combine(TODAY, datetime.min.time(), UTC) + timedelta(hours=20)

    def stats(self, logs, blocks, term_start=date(2026, 6, 1)):
        return streak_stats(logs and [], logs, blocks, term_start, "UTC", self.NOW)

    def test_buckets(self):
        self.assertEqual([_bucket(0), _bucket(30), _bucket(90), _bucket(180), _bucket(300)],
                         [0, 1, 2, 3, 4])

    def test_rest_day_does_not_break_streak(self):
        # Jun 12 met (planned 60, used 40>=30), Jun 13 REST (nothing planned),
        # Jun 14 today met. Streak should span all three.
        logs = [Log(date(2026, 6, 12), 40), Log(date(2026, 6, 14), 60)]
        blocks = [Block(date(2026, 6, 12), 60), Block(date(2026, 6, 14), 60)]
        s = self.stats(logs, blocks)
        self.assertEqual(s["current"], 3)

    def test_missed_planned_day_breaks_streak(self):
        # Jun 13 planned 120 but used 0 -> breaks. Today Jun 14 met.
        logs = [Log(date(2026, 6, 14), 60)]
        blocks = [Block(date(2026, 6, 13), 120), Block(date(2026, 6, 14), 60)]
        s = self.stats(logs, blocks)
        self.assertEqual(s["current"], 1)   # only today

    def test_today_pending_does_not_break(self):
        # today planned 60 but nothing used yet; yesterday met -> streak = 1 (yesterday)
        logs = [Log(date(2026, 6, 13), 60)]
        blocks = [Block(date(2026, 6, 13), 60), Block(date(2026, 6, 14), 60)]
        s = self.stats(logs, blocks)
        self.assertEqual(s["current"], 1)

    def test_totals_and_delta(self):
        logs = [Log(date(2026, 6, 14), 60), Log(date(2026, 6, 13), 30)]
        s = self.stats(logs, [])
        self.assertEqual(s["today_min"], 60)
        self.assertEqual(s["yesterday_min"], 30)
        self.assertEqual(s["today_delta"], 100)   # 60 vs 30 = +100%

    def test_future_planned_cell_flagged(self):
        blocks = [Block(date(2026, 6, 20), 90)]   # future
        s = self.stats([], blocks)
        fut = [c for c in s["cells"] if c["day"] == "2026-06-20"][0]
        self.assertTrue(fut["future"])
        self.assertEqual(fut["plevel"], 2)


if __name__ == "__main__":
    unittest.main()
