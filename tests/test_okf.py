import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import (
    add_lesson_block, create_track_from_spec, get_or_create_lesson_for_node, get_track_tree,
)
from app.okf import export_filename, export_track_okf, import_track_okf
from app.source_store import create_source, link_source_to_track


class TestOkf(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _seed_track(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics", "Loops"]})
        node_id = tree["modules"][0]["nodes"][0]["id"]
        lesson = get_or_create_lesson_for_node(self.session, node_id)
        add_lesson_block(self.session, lesson["id"], {
            "block_type": "quiz",
            "title": "Check",
            "payload": {"question": "What is a variable?", "options": ["a name bound to a value", "a loop"], "correct_index": 0},
        })
        source = create_source(self.session, {"title": "Notes", "source_type": "text", "body_text": "Variables store references to values."})
        link_source_to_track(self.session, tree["id"], source["id"], "primary")
        return tree

    def test_export_returns_none_for_missing_track(self):
        self.assertIsNone(export_track_okf(self.session, 999))

    def test_export_includes_modules_lessons_and_sources(self):
        tree = self._seed_track()
        bundle = export_track_okf(self.session, tree["id"])

        self.assertEqual(bundle["okf_version"], 1)
        self.assertEqual(bundle["track"]["title"], "Python Course")
        self.assertEqual(len(bundle["modules"]), 2)
        first_node = bundle["modules"][0]["nodes"][0]
        self.assertIsNotNone(first_node["lesson"])
        block_types = [b["block_type"] for b in first_node["lesson"]["blocks"]]
        self.assertIn("quiz", block_types)
        self.assertEqual(len(bundle["sources"]), 1)
        self.assertEqual(bundle["sources"][0]["body_text"], "Variables store references to values.")

    def test_export_filename_is_slugified(self):
        tree = self._seed_track()
        bundle = export_track_okf(self.session, tree["id"])
        self.assertEqual(export_filename(bundle), "python-course.okf.json")

    def test_import_round_trip_recreates_matching_structure(self):
        original_tree = self._seed_track()
        bundle = export_track_okf(self.session, original_tree["id"])

        result = import_track_okf(self.session, bundle)
        imported = result["track"]

        self.assertNotEqual(imported["id"], original_tree["id"])
        self.assertEqual(imported["title"], original_tree["title"])
        self.assertEqual(len(imported["modules"]), len(original_tree["modules"]))
        self.assertEqual(
            [m["title"] for m in imported["modules"]],
            [m["title"] for m in original_tree["modules"]],
        )

        imported_first_node = imported["modules"][0]["nodes"][0]
        imported_lesson = get_or_create_lesson_for_node(self.session, imported_first_node["id"])
        imported_block_types = [b["block_type"] for b in imported_lesson["blocks"]]
        self.assertIn("quiz", imported_block_types)

        # Sources came back chunked (chunk_registered_source runs during import).
        from app.source_store import list_track_sources
        sources = list_track_sources(self.session, imported["id"])
        self.assertEqual(len(sources), 1)
        self.assertGreaterEqual(sources[0]["chunk_count"], 1)

    def test_import_rejects_invalid_bundle(self):
        with self.assertRaises(ValueError):
            import_track_okf(self.session, {"not": "a bundle"})

    def test_import_reuses_existing_source_on_matching_content(self):
        original_tree = self._seed_track()
        bundle = export_track_okf(self.session, original_tree["id"])

        import_track_okf(self.session, bundle)
        import_track_okf(self.session, bundle)

        # create_source dedupes by content hash, so importing the same bundle
        # twice should not create two copies of the same source text.
        from sqlmodel import select
        from app.models import LearningSource
        matching = self.session.exec(
            select(LearningSource).where(LearningSource.body_text == "Variables store references to values.")
        ).all()
        self.assertEqual(len(matching), 1)


if __name__ == "__main__":
    unittest.main()
