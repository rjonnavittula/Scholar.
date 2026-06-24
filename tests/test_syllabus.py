import unittest
from datetime import date

from app.syllabus import parse_syllabus, find_dates


class TestSyllabusParser(unittest.TestCase):
    def test_us_month_day(self):
        items = parse_syllabus("Homework 1 due September 12, 2025", default_year=2025)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["due_date"], "2025-09-12")
        self.assertEqual(items[0]["category"], "Homework")
        self.assertIn("Homework 1", items[0]["title"])

    def test_intl_day_month(self):
        items = parse_syllabus("Assignment 2 submission by 13 September 2025", default_year=2025)
        self.assertEqual(items[0]["due_date"], "2025-09-13")

    def test_numeric_dayfirst_inferred_when_gt_12(self):
        # 13/09 can only be day/month
        items = parse_syllabus("Quiz 1 due 13/09/2025", default_year=2025)
        self.assertEqual(items[0]["due_date"], "2025-09-13")
        self.assertEqual(items[0]["category"], "Quiz")

    def test_numeric_us_default(self):
        items = parse_syllabus("Lab report due 9/12/2025", default_year=2025)
        self.assertEqual(items[0]["due_date"], "2025-09-12")

    def test_numeric_dayfirst_flag(self):
        items = parse_syllabus("Essay due 4/5/2025", default_year=2025, dayfirst=True)
        self.assertEqual(items[0]["due_date"], "2025-05-04")
        items_us = parse_syllabus("Essay due 4/5/2025", default_year=2025, dayfirst=False)
        self.assertEqual(items_us[0]["due_date"], "2025-04-05")

    def test_iso_date(self):
        items = parse_syllabus("Final project deadline 2025-12-10", default_year=2025)
        self.assertEqual(items[0]["due_date"], "2025-12-10")
        self.assertEqual(items[0]["category"], "Project")

    def test_year_inferred_from_default(self):
        items = parse_syllabus("Midterm exam on October 5", default_year=2024)
        self.assertEqual(items[0]["due_date"], "2024-10-05")
        self.assertEqual(items[0]["category"], "Exam")

    def test_academic_rollover_spring_next_year(self):
        text = "Reading due September 3\nFinal paper due January 20"
        items = parse_syllabus(text, default_year=2025)
        by_cat = {i["category"]: i["due_date"] for i in items}
        self.assertEqual(by_cat["Reading"], "2025-09-03")
        self.assertEqual(by_cat["Project"], "2026-01-20")   # rolled to next year

    def test_lines_without_keywords_ignored(self):
        items = parse_syllabus("Office hours: Tuesdays 3pm in room 201", default_year=2025)
        self.assertEqual(items, [])

    def test_lines_without_dates_ignored(self):
        items = parse_syllabus("Homework will be assigned regularly", default_year=2025)
        self.assertEqual(items, [])

    def test_dedup(self):
        text = "HW1 due Sep 12\nHW1 due Sep 12"
        items = parse_syllabus(text, default_year=2025)
        self.assertEqual(len(items), 1)

    def test_sorted_by_due(self):
        text = "Quiz due Oct 10\nHomework due Sep 5\nExam due Nov 1"
        items = parse_syllabus(text, default_year=2025)
        self.assertEqual([i["due_date"] for i in items], ["2025-09-05", "2025-10-10", "2025-11-01"])

    def test_due_keyword_picks_following_date(self):
        # week-of date then the actual due date; should prefer the one after "due"
        items = parse_syllabus("Week of Sep 8 - Problem Set 3 due Sep 14", default_year=2025)
        self.assertEqual(items[0]["due_date"], "2025-09-14")

    def test_find_dates_orders_and_parses(self):
        ds = find_dates("read ch 2 by 12 March 2026", 2026)
        self.assertEqual((ds[0]["m"], ds[0]["d"], ds[0]["y"]), (3, 12, 2026))


if __name__ == "__main__":
    unittest.main()
