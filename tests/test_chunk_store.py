import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.chunk_store import create_source_chunk, estimate_tokens, list_source_chunks
from app.source_store import create_source, delete_source, list_source_sections, parse_registered_source


class TestChunkStore(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_create_and_list_source_chunk(self):
        source = create_source(self.session, {
            "title": "Python Notes",
            "source_type": "markdown",
            "body_text": "# Python Basics\nVariables store references.",
        })
        parse_registered_source(self.session, source["id"])
        section = list_source_sections(self.session, source["id"])[0]

        chunk = create_source_chunk(self.session, {
            "source_id": source["id"],
            "section_id": section["id"],
            "heading": section["heading"],
            "heading_path": section["metadata"]["heading_path"],
            "body_text": section["body_text"],
            "metadata": {"strategy": "manual-test"},
        })

        self.assertEqual(chunk["source_id"], source["id"])
        self.assertEqual(chunk["section_id"], section["id"])
        self.assertEqual(chunk["position"], 1)
        self.assertEqual(chunk["section_position"], 1)
        self.assertEqual(chunk["heading_path"], ["Python Basics"])
        self.assertEqual(chunk["char_count"], len("Variables store references."))
        self.assertGreater(chunk["token_estimate"], 0)
        self.assertEqual(chunk["metadata"]["strategy"], "manual-test")

        rows = list_source_chunks(self.session, source["id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["chunk_hash"], chunk["chunk_hash"])

    def test_chunk_positions_increment(self):
        source = create_source(self.session, {"title": "Python Notes", "body_text": "one two three"})

        first = create_source_chunk(self.session, {"source_id": source["id"], "body_text": "one"})
        second = create_source_chunk(self.session, {"source_id": source["id"], "body_text": "two"})

        self.assertEqual(first["position"], 1)
        self.assertEqual(second["position"], 2)

    def test_chunk_requires_source_and_body(self):
        source = create_source(self.session, {"title": "Python Notes", "body_text": "one two three"})

        with self.assertRaises(ValueError):
            create_source_chunk(self.session, {"source_id": 999, "body_text": "x"})
        with self.assertRaises(ValueError):
            create_source_chunk(self.session, {"source_id": source["id"], "body_text": ""})

    def test_chunk_rejects_section_from_other_source(self):
        source_a = create_source(self.session, {"title": "A", "body_text": "# A\nAlpha."})
        source_b = create_source(self.session, {"title": "B", "body_text": "# B\nBeta."})
        parse_registered_source(self.session, source_a["id"])
        section_a = list_source_sections(self.session, source_a["id"])[0]

        with self.assertRaises(ValueError):
            create_source_chunk(self.session, {
                "source_id": source_b["id"],
                "section_id": section_a["id"],
                "body_text": "wrong source",
            })

    def test_delete_source_removes_chunks(self):
        source = create_source(self.session, {"title": "Python Notes", "body_text": "one two three"})
        create_source_chunk(self.session, {"source_id": source["id"], "body_text": "one"})

        self.assertEqual(len(list_source_chunks(self.session, source["id"])), 1)
        self.assertTrue(delete_source(self.session, source["id"]))
        self.assertIsNone(list_source_chunks(self.session, source["id"]))

    def test_token_estimate_is_stable_and_nonzero(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("hello"), 1)
        self.assertEqual(estimate_tokens("one two three four"), 5)


if __name__ == "__main__":
    unittest.main()
