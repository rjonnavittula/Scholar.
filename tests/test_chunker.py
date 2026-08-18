import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.chunker import CHUNKER_VERSION, build_chunk_specs, chunk_registered_source, split_text_for_chunks
from app.chunk_store import list_source_chunks
from app.source_store import create_source, list_source_sections, parse_registered_source


class TestChunker(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_short_section_becomes_one_chunk(self):
        source = create_source(self.session, {
            "title": "Python Notes",
            "source_type": "markdown",
            "body_text": "# Variables\nVariables store references.",
        })
        parse_registered_source(self.session, source["id"])

        result = chunk_registered_source(self.session, source["id"])

        self.assertEqual(result["chunker_version"], CHUNKER_VERSION)
        self.assertEqual(result["chunk_count"], 1)
        chunk = result["chunks"][0]
        self.assertEqual(chunk["heading"], "Variables")
        self.assertEqual(chunk["heading_path"], ["Variables"])
        self.assertEqual(chunk["metadata"]["chunker_version"], CHUNKER_VERSION)
        self.assertEqual(chunk["metadata"]["split_count"], 1)

    def test_long_section_splits_with_overlap(self):
        text = " ".join(f"word{i}" for i in range(220))
        chunks = split_text_for_chunks(text, max_chars=260, overlap_chars=40)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 260 for chunk in chunks))
        self.assertTrue(chunks[1].split()[0] in chunks[0] or chunks[0].split()[-1] in chunks[1])


    def test_overlap_never_starts_inside_word(self):
        text = " ".join(f"token{i}" for i in range(260))
        chunks = split_text_for_chunks(text, max_chars=320, overlap_chars=40)

        self.assertGreater(len(chunks), 2)
        for chunk in chunks[1:]:
            first_word = chunk.split()[0]
            self.assertRegex(first_word, r"^token\d+$")

    def test_replace_false_does_not_duplicate_existing_chunks(self):
        body = "# Python\n" + " ".join(f"token{i}" for i in range(180))
        source = create_source(self.session, {
            "title": "Python Notes",
            "source_type": "markdown",
            "body_text": body,
        })

        first = chunk_registered_source(self.session, source["id"], max_chars=320, overlap_chars=40, replace=False)
        second = chunk_registered_source(self.session, source["id"], max_chars=320, overlap_chars=40, replace=False)

        self.assertEqual(first["chunk_count"], second["chunk_count"])
        self.assertEqual(len(list_source_chunks(self.session, source["id"])), first["chunk_count"])

    def test_chunk_registered_source_replaces_old_chunks(self):
        body = "# Python\n" + " ".join(f"token{i}" for i in range(160))
        source = create_source(self.session, {
            "title": "Python Notes",
            "source_type": "markdown",
            "body_text": body,
        })
        parse_registered_source(self.session, source["id"])

        first = chunk_registered_source(self.session, source["id"], max_chars=260, overlap_chars=30)
        second = chunk_registered_source(self.session, source["id"], max_chars=260, overlap_chars=30)

        self.assertEqual(first["chunk_count"], second["chunk_count"])
        self.assertEqual(len(list_source_chunks(self.session, source["id"])), second["chunk_count"])
        self.assertEqual([c["position"] for c in second["chunks"]], list(range(1, second["chunk_count"] + 1)))

    def test_build_specs_preserves_section_metadata(self):
        source = create_source(self.session, {
            "title": "Course Notes",
            "source_type": "markdown",
            "body_text": "Course\n======\n\n## Functions\nFunctions package behavior.",
        })
        parse_registered_source(self.session, source["id"])
        sections = list_source_sections(self.session, source["id"])

        specs = build_chunk_specs(source["id"], sections, max_chars=300, overlap_chars=0)

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["heading_path"], ["Course", "Functions"])
        self.assertEqual(specs[0]["metadata"]["source_section_heading"], "Functions")
        self.assertEqual(specs[0]["metadata"]["source_section_position"], 1)

    def test_chunk_missing_source_returns_none(self):
        self.assertIsNone(chunk_registered_source(self.session, 999))

    def test_chunker_auto_parses_registered_source(self):
        source = create_source(self.session, {
            "title": "Auto Parse Notes",
            "source_type": "markdown",
            "body_text": "# Basics\nVariables store references.",
        })

        result = chunk_registered_source(self.session, source["id"])

        self.assertEqual(result["chunk_count"], 1)
        self.assertEqual(result["chunks"][0]["heading"], "Basics")


if __name__ == "__main__":
    unittest.main()
