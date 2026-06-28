import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import create_track_from_spec
from app.source_store import (
    create_source, delete_source, get_source, link_source_to_track, list_sources,
    list_source_sections, list_track_sources, parse_registered_source,
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
        self.assertEqual(parsed["outline"][0]["heading"], "Python Basics")

        sections = list_source_sections(self.session, source["id"])
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[1]["heading"], "Functions")

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
