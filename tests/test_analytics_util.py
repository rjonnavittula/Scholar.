import unittest
from datetime import date
from app.analytics_util import range_bounds, week_label, recent_weeks, forward_weeks, to_csv


class AnalyticsUtilTests(unittest.TestCase):
    # Sunday Jun 14 2026 (weekday 6); that week's Monday is Jun 8.
    DAY = date(2026, 6, 14)

    def test_today_yesterday(self):
        self.assertEqual(range_bounds("today", self.DAY), (self.DAY, self.DAY))
        self.assertEqual(range_bounds("yesterday", self.DAY), (date(2026, 6, 13), date(2026, 6, 13)))

    def test_this_week_monday_anchored(self):
        s, e = range_bounds("this_week", self.DAY)
        self.assertEqual((s, e), (date(2026, 6, 8), date(2026, 6, 14)))

    def test_last_week(self):
        s, e = range_bounds("last_week", self.DAY)
        self.assertEqual((s, e), (date(2026, 6, 1), date(2026, 6, 7)))

    def test_last_7_and_30(self):
        self.assertEqual(range_bounds("last_7", self.DAY), (date(2026, 6, 8), self.DAY))
        self.assertEqual(range_bounds("last_30", self.DAY), (date(2026, 5, 16), self.DAY))

    def test_this_and_last_month(self):
        self.assertEqual(range_bounds("this_month", self.DAY), (date(2026, 6, 1), date(2026, 6, 30)))
        self.assertEqual(range_bounds("last_month", self.DAY), (date(2026, 5, 1), date(2026, 5, 31)))

    def test_all_is_unbounded(self):
        self.assertEqual(range_bounds("all", self.DAY), (None, None))

    def test_week_label_same_and_cross_month(self):
        self.assertEqual(week_label(date(2026, 6, 14)), "Jun 8 \u2013 14")
        self.assertEqual(week_label(date(2026, 7, 1)), "Jun 29 \u2013 Jul 5")

    def test_recent_weeks_count_and_order(self):
        wk = recent_weeks(self.DAY, 6)
        self.assertEqual(len(wk), 6)
        self.assertEqual(wk[-1][1], "Jun 8 \u2013 14")          # newest last
        self.assertTrue(wk[0][0] < wk[-1][0])                    # oldest first

    def test_forward_weeks(self):
        wk = forward_weeks(self.DAY, 10)
        self.assertEqual(len(wk), 10)
        self.assertEqual(wk[0][1], "Jun 8 \u2013 14")            # this week first
        self.assertTrue(wk[0][0] < wk[1][0])                     # ascending

    def test_to_csv_header_and_quoting(self):
        out = to_csv(["task", "minutes"],
                     [{"task": "PS4, part 1", "minutes": 45}, {"task": "Lab", "minutes": 30}])
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "task,minutes")
        self.assertEqual(lines[1], '"PS4, part 1",45')          # comma triggers quoting
        self.assertEqual(lines[2], "Lab,30")

    def test_to_csv_missing_key_blank(self):
        out = to_csv(["a", "b"], [{"a": 1}])
        self.assertEqual(out.strip().splitlines()[1], "1,")


if __name__ == "__main__":
    unittest.main()
