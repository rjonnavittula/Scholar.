import unittest

from app.source_upload import build_upload_source_spec, infer_source_type


class TestSourceUpload(unittest.TestCase):
    def test_markdown_upload_becomes_source_spec(self):
        spec = build_upload_source_spec(
            filename="python-basics.md",
            content_type="text/markdown",
            data=b"# Python Basics\nVariables store references.",
            trust_level="course",
        )

        self.assertEqual(spec["title"], "python basics")
        self.assertEqual(spec["source_type"], "markdown")
        self.assertEqual(spec["trust_level"], "course")
        self.assertEqual(spec["original_name"], "python-basics.md")
        self.assertIn("Variables", spec["body_text"])
        self.assertEqual(spec["metadata"]["origin"], "file-upload")

    def test_text_upload_can_override_title_and_type(self):
        spec = build_upload_source_spec(
            filename="notes.py",
            content_type="text/x-python",
            data=b"def hello():\n    return 'world'\n",
            title="Python Code Notes",
            source_type="text",
        )

        self.assertEqual(spec["title"], "Python Code Notes")
        self.assertEqual(spec["source_type"], "text")
        self.assertIn("def hello", spec["body_text"])

    def test_infer_pdf(self):
        self.assertEqual(infer_source_type("lecture.pdf", "application/pdf"), "pdf")

    def test_empty_and_oversized_uploads_are_rejected(self):
        with self.assertRaises(ValueError):
            build_upload_source_spec(filename="empty.txt", content_type="text/plain", data=b"")
        with self.assertRaises(ValueError):
            build_upload_source_spec(filename="huge.txt", content_type="text/plain", data=b"x" * (8 * 1024 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()
