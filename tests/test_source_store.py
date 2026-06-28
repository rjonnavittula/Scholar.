import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import create_track_from_spec
from app.source_store import (
    create_source, delete_source, get_source, link_source_to_track, list_sources,
    list_track_sources,
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

    def test_source_requires_body_and_known_type(self):
        with self.assertRaises(ValueError):
            create_source(self.session, {"title": "Empty", "body_text": ""})
        with self.assertRaises(ValueError):
            create_source(self.session, {"source_type": "exe", "body_text": "x"})

    def test_link_source_to_track(self):
        track = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Basics Notes", "body_text": "Variables and functions."})

        linked = link_source_to_track(self.session, track["id"], source["id"], role="primary")
        self.assertEqual(linked["id"], source["id"])

        rows = list_track_sources(self.session, track["id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role"], "primary")

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
