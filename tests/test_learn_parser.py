import unittest

from app.learn_parser import classify_input, extract_modules, extract_track_title, parse_source


class LearnParserTests(unittest.TestCase):
    def test_classifies_system_prompt(self):
        text = "System Prompt\nRole & Persona\nYou are a tutor."
        self.assertEqual(classify_input(text), "system_prompt")

    def test_classifies_syllabus(self):
        text = "Course Syllabus\nGrading: exams and labs"
        self.assertEqual(classify_input(text), "syllabus")

    def test_extracts_modules(self):
        text = "Module 1: Upper Limb\nChapter 2: Thorax\nUnit 3: Abdomen"
        self.assertEqual(extract_modules(text), ["Upper Limb", "Thorax", "Abdomen"])

    def test_parse_source_has_hash_modules_and_course_title(self):
        out = parse_source("Module 1: Python Basics")
        self.assertEqual(out["track_title"], "Python Course")
        self.assertEqual(out["modules"], ["Python Basics"])
        self.assertEqual(len(out["source_hash"]), 16)

    def test_extract_track_title_ignores_system_prompt_heading(self):
        text = """
System Prompt
Role & Persona
You are the Python Mentor.

Module 1: Python Basics
Module 2: Functions
"""
        self.assertEqual(extract_track_title(text), "Python Course")

    def test_parse_source_buckets_rules(self):
        out = parse_source("""
System Prompt
Role & Persona: The Anatomical Mentor
Module 1: Upper Limb
You must ask active recall questions.
Use visual diagrams for spatial relations.
Quiz before revealing answers.
""")
        self.assertEqual(out["input_type"], "system_prompt")
        self.assertEqual(out["role"], "The Anatomical Mentor")
        self.assertEqual(out["modules"], ["Upper Limb"])
        self.assertTrue(out["teaching_rules"])
        self.assertTrue(out["visual_rules"])
        self.assertTrue(out["assessment_rules"])


if __name__ == "__main__":
    unittest.main()
