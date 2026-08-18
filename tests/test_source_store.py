import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.chunker import chunk_registered_source
from app.learn_store import create_track_from_spec
from app.source_store import (
    create_source, delete_source, get_source, get_source_audit, link_source_to_track, list_sources,
    list_source_sections, list_track_sources, parse_registered_source, unlink_source_from_track,
)


class TestSourceStore(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_create_and_list_source(self):
        source = create_source(self.session, {
            "title": "Python Notes",
            "source_type": "markdown",
            "trust_level": "user",
            "body_text": "# Python Notes\nVariables store references.",
            "metadata": {"course": "Python"},
        })

        self.assertEqual(source["title"], "Python Notes")
        self.assertEqual(source["source_type"], "markdown")
        self.assertEqual(source["char_count"], len("# Python Notes\nVariables store references."))
        self.assertIn("body_text", get_source(self.session, source["id"]))
        self.assertEqual(list_sources(self.session)[0]["title"], "Python Notes")


    def test_duplicate_source_reuses_existing_row(self):
        spec = {
            "title": "Python Notes",
            "source_type": "markdown",
            "trust_level": "user",
            "body_text": "# Python Notes\nVariables store references.",
        }
        first = create_source(self.session, spec)
        second = create_source(self.session, {**spec, "title": "Duplicate Title"})

        self.assertEqual(second["id"], first["id"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual(len(list_sources(self.session)), 1)


    def test_parse_registered_source_persists_sections(self):
        source = create_source(self.session, {
            "title": "Python Notes",
            "source_type": "markdown",
            "trust_level": "user",
            "body_text": "# Python Basics\nVariables store references.\n\n## Functions\nFunctions package behavior.",
        })

        parsed = parse_registered_source(self.session, source["id"])

        self.assertEqual(parsed["source"]["status"], "parsed")
        self.assertEqual(parsed["section_count"], 2)
        self.assertEqual(parsed["source"]["section_count"], 2)
        self.assertEqual(get_source(self.session, source["id"])["section_count"], 2)
        self.assertEqual(parsed["outline"][0]["heading"], "Python Basics")

        sections = list_source_sections(self.session, source["id"])
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[1]["heading"], "Functions")
        self.assertEqual(sections[1]["metadata"]["parser_version"], "source-parser-v2")
        self.assertEqual(sections[1]["metadata"]["heading_path"], ["Python Basics", "Functions"])
        self.assertEqual(list_sources(self.session)[0]["section_count"], 2)

    def test_source_reports_chunk_count_after_chunking(self):
        source = create_source(self.session, {
            "title": "Python Notes",
            "source_type": "markdown",
            "body_text": "# Python Basics\nVariables store references.",
        })

        result = chunk_registered_source(self.session, source["id"])

        self.assertEqual(result["chunk_count"], 1)
        self.assertEqual(get_source(self.session, source["id"])["chunk_count"], 1)
        self.assertEqual(list_sources(self.session)[0]["chunk_count"], 1)

    def test_parse_registered_source_is_idempotent(self):
        source = create_source(self.session, {
            "title": "Python Notes",
            "source_type": "markdown",
            "body_text": "# Python Basics\nVariables.\n\n## Functions\nFunctions.",
        })

        parse_registered_source(self.session, source["id"])
        parse_registered_source(self.session, source["id"])

        self.assertEqual(len(list_source_sections(self.session, source["id"])), 2)

    def test_source_requires_body_and_known_type(self):
        with self.assertRaises(ValueError):
            create_source(self.session, {"title": "Empty", "body_text": ""})
        with self.assertRaises(ValueError):
            create_source(self.session, {"source_type": "exe", "body_text": "x"})
        with self.assertRaises(ValueError):
            create_source(self.session, {"title": "Huge", "body_text": "x" * 250_001})

    def test_source_allows_ui_trust_and_transcript_values(self):
        source = create_source(self.session, {
            "title": "Lecture Transcript",
            "source_type": "transcript",
            "trust_level": "instructor",
            "body_text": "Welcome to Python basics.",
        })

        self.assertEqual(source["source_type"], "transcript")
        self.assertEqual(source["trust_level"], "instructor")

    def test_link_source_to_track(self):
        track = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Basics Notes", "body_text": "Variables and functions."})

        linked = link_source_to_track(self.session, track["id"], source["id"], role="primary")
        self.assertEqual(linked["id"], source["id"])
        self.assertEqual(linked["role"], "primary")

        linked_again = link_source_to_track(self.session, track["id"], source["id"], role="supplemental")
        self.assertEqual(linked_again["id"], source["id"])
        self.assertEqual(linked_again["role"], "supplemental")

        rows = list_track_sources(self.session, track["id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role"], "supplemental")

    def test_link_source_rejects_unknown_role(self):
        track = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Basics Notes", "body_text": "Variables."})

        with self.assertRaises(ValueError):
            link_source_to_track(self.session, track["id"], source["id"], role="admin")


    def test_unlink_source_from_track(self):
        track = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Basics Notes", "body_text": "Variables."})
        link_source_to_track(self.session, track["id"], source["id"])

        self.assertTrue(unlink_source_from_track(self.session, track["id"], source["id"]))
        self.assertEqual(list_track_sources(self.session, track["id"]), [])
        self.assertFalse(unlink_source_from_track(self.session, track["id"], source["id"]))
        self.assertIsNone(unlink_source_from_track(self.session, 999, source["id"]))

    def test_source_audit_reports_phase_b_counts(self):
        track = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        source = create_source(self.session, {
            "title": "Basics Notes",
            "source_type": "markdown",
            "body_text": "# Basics\nVariables.",
        })
        parse_registered_source(self.session, source["id"])
        link_source_to_track(self.session, track["id"], source["id"], role="reference")

        audit = get_source_audit(self.session)

        self.assertEqual(audit["phase"], "C")
        self.assertEqual(audit["status"], "parsed")
        self.assertEqual(audit["total_sources"], 1)
        self.assertEqual(audit["linked_sources"], 1)
        self.assertEqual(audit["parsed_sources"], 1)
        self.assertEqual(audit["chunked_sources"], 0)
        self.assertEqual(audit["unchunked_parsed_sources"], 1)
        self.assertEqual(audit["total_sections"], 1)
        self.assertEqual(audit["total_chunks"], 0)
        self.assertEqual(audit["avg_chunk_tokens"], 0)
        self.assertIn("markdown", audit["source_types"])


    def test_source_audit_reports_chunk_counts_for_phase_c(self):
        source = create_source(self.session, {
            "title": "Chunked Notes",
            "source_type": "markdown",
            "body_text": "# Basics\n" + " ".join(f"token{i}" for i in range(120)),
        })
        chunk_registered_source(self.session, source["id"], max_chars=320, overlap_chars=40)

        audit = get_source_audit(self.session)

        self.assertEqual(audit["phase"], "C")
        self.assertEqual(audit["status"], "ready")
        self.assertEqual(audit["chunked_sources"], 1)
        self.assertEqual(audit["unchunked_parsed_sources"], 0)
        self.assertGreater(audit["total_chunks"], 0)
        self.assertGreater(audit["total_chunk_tokens"], 0)
        self.assertGreater(audit["avg_chunk_tokens"], 0)

    def test_delete_source_removes_links(self):
        track = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Basics Notes", "body_text": "Variables."})
        link_source_to_track(self.session, track["id"], source["id"])

        self.assertTrue(delete_source(self.session, source["id"]))
        self.assertIsNone(get_source(self.session, source["id"]))
        self.assertEqual(list_track_sources(self.session, track["id"]), [])
        self.assertFalse(delete_source(self.session, source["id"]))


if __name__ == "__main__":
    unittest.main()
