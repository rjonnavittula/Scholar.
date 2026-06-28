import unittest

from app.source_parser import parse_pasted_source


class TestSourceParser(unittest.TestCase):
    def test_markdown_headings_become_sections(self):
        parsed = parse_pasted_source("# Python Basics\nVariables store references.\n\n## Functions\nFunctions package behavior.", "markdown")

        self.assertEqual(parsed["section_count"], 2)
        self.assertEqual(parsed["outline"][0]["heading"], "Python Basics")
        self.assertEqual(parsed["outline"][1]["heading"], "Functions")
        self.assertIn("Variables", parsed["sections"][0]["body_text"])
        self.assertEqual(parsed["sections"][1]["level"], 2)

    def test_plain_text_numbered_headings(self):
        parsed = parse_pasted_source("Module 1: Variables\nNames point to objects.\n\nModule 2: Functions\nReusable behavior.", "text")

        self.assertEqual(parsed["section_count"], 2)
        self.assertEqual(parsed["outline"][0]["heading"], "Variables")
        self.assertEqual(parsed["outline"][1]["heading"], "Functions")

    def test_no_heading_falls_back_to_overview(self):
        parsed = parse_pasted_source("Variables store references.\nFunctions package reusable behavior.", "text")

        self.assertEqual(parsed["section_count"], 1)
        self.assertEqual(parsed["sections"][0]["heading"], "Overview")
        self.assertIn("Variables", parsed["sections"][0]["body_text"])

    def test_empty_text_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_pasted_source("   ", "markdown")


if __name__ == "__main__":
    unittest.main()
