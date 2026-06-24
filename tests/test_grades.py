import unittest

from app.grades import compute_grade, letter


class TestGrades(unittest.TestCase):
    def test_letter_scale(self):
        self.assertEqual(letter(95), "A")
        self.assertEqual(letter(90), "A-")
        self.assertEqual(letter(88), "B+")
        self.assertEqual(letter(59), "F")
        self.assertEqual(letter(None), "")

    def test_single_category(self):
        cats = [{"name": "HW", "weight": 100, "items": [
            {"earned": 18, "possible": 20}, {"earned": 9, "possible": 10}]}]
        r = compute_grade(cats)
        self.assertEqual(r["percent"], 90.0)        # 27/30
        self.assertEqual(r["letter"], "A-")

    def test_weighted_mix(self):
        cats = [
            {"name": "HW", "weight": 40, "items": [{"earned": 90, "possible": 100}]},   # 90
            {"name": "Exam", "weight": 60, "items": [{"earned": 80, "possible": 100}]}, # 80
        ]
        r = compute_grade(cats)
        self.assertEqual(r["percent"], 84.0)        # .4*90 + .6*80
        self.assertEqual(r["letter"], "B")

    def test_ungraded_category_excluded(self):
        # Final has weight but no items yet — should not drag the grade down
        cats = [
            {"name": "HW", "weight": 50, "items": [{"earned": 95, "possible": 100}]},
            {"name": "Final", "weight": 50, "items": []},
        ]
        r = compute_grade(cats)
        self.assertEqual(r["percent"], 95.0)        # normalized over graded weight only
        self.assertEqual(r["weight_graded"], 50.0)

    def test_no_grades_yet(self):
        r = compute_grade([{"name": "HW", "weight": 100, "items": []}])
        self.assertIsNone(r["percent"])
        self.assertEqual(r["letter"], "")

    def test_zero_possible_ignored(self):
        cats = [{"name": "HW", "weight": 100, "items": [
            {"earned": 0, "possible": 0}, {"earned": 8, "possible": 10}]}]
        r = compute_grade(cats)
        self.assertEqual(r["percent"], 80.0)

    def test_empty(self):
        r = compute_grade([])
        self.assertIsNone(r["percent"])


if __name__ == "__main__":
    unittest.main()
