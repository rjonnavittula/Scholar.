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

    def test_pdf_page_markers_become_sections(self):
        parsed = parse_pasted_source("Page 1\nVariables.\n\nPage 2\nFunctions.", "pdf")

        self.assertEqual(parsed["section_count"], 2)
        self.assertEqual(parsed["outline"][0]["heading"], "Page 1")
        self.assertEqual(parsed["outline"][1]["heading"], "Page 2")
        self.assertIn("Functions", parsed["sections"][1]["body_text"])


    def test_setext_headings_become_sections(self):
        parsed = parse_pasted_source("Python Basics\n=============\nVariables store references.\n\nFunctions\n---------\nFunctions package behavior.", "markdown")

        self.assertEqual(parsed["section_count"], 2)
        self.assertEqual(parsed["outline"][0]["heading"], "Python Basics")
        self.assertEqual(parsed["sections"][1]["level"], 2)
        self.assertEqual(parsed["sections"][0]["metadata"]["heading_kind"], "setext")

    def test_consecutive_headings_skip_empty_parent_but_keep_path(self):
        parsed = parse_pasted_source("# Python Course\n## Variables\nNames point to objects.", "markdown")

        self.assertEqual(parsed["section_count"], 1)
        self.assertEqual(parsed["sections"][0]["heading"], "Variables")
        self.assertEqual(parsed["sections"][0]["metadata"]["heading_path"], ["Python Course", "Variables"])

    def test_code_fence_headings_are_not_parsed(self):
        parsed = parse_pasted_source("# Python Basics\n```python\n# not a section\nx = 1\n```\nVariables store references.", "markdown")

        self.assertEqual(parsed["section_count"], 1)
        self.assertEqual(parsed["outline"][0]["heading"], "Python Basics")
        self.assertIn("# not a section", parsed["sections"][0]["body_text"])

    def test_parser_normalizes_hyphenated_line_breaks(self):
        parsed = parse_pasted_source("# Python Basics\nVariables store refer-\nences to objects.", "markdown")

        self.assertIn("references", parsed["sections"][0]["body_text"])
        self.assertNotIn("refer-\nences", parsed["sections"][0]["body_text"])

    def test_plain_text_bullets_are_not_headings(self):
        parsed = parse_pasted_source("Python Basics\n- Variables\n- Functions", "text")

        self.assertEqual(parsed["section_count"], 1)
        self.assertEqual(parsed["sections"][0]["heading"], "Python Basics")
        self.assertIn("- Variables", parsed["sections"][0]["body_text"])

    def test_pdf_page_of_markers_become_sections(self):
        parsed = parse_pasted_source("--- Page 1 of 2 ---\nVariables.\n\nPage 2 / 2\nFunctions.", "pdf")

        self.assertEqual(parsed["section_count"], 2)
        self.assertEqual(parsed["outline"][0]["heading"], "Page 1")
        self.assertEqual(parsed["outline"][1]["heading"], "Page 2")


    def test_pdf_form_feed_markers_become_sections(self):
        parsed = parse_pasted_source("Page 1\nVariables.\n\f\nFunctions.", "pdf")

        self.assertEqual(parsed["section_count"], 2)
        self.assertEqual(parsed["outline"][0]["heading"], "Page 1")
        self.assertEqual(parsed["outline"][1]["heading"], "Page 2")

    def test_empty_text_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_pasted_source("   ", "markdown")


if __name__ == "__main__":
    unittest.main()
