import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import (
    add_lesson_block, create_track_from_spec, get_lesson_tree, get_or_create_lesson_for_node,
    get_track_tree, list_tracks,
)


class TestLearnStore(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_create_track_from_spec_builds_modules_and_nodes(self):
        tree = create_track_from_spec(self.session, {
            "track_title": "Anatomy",
            "input_type": "system_prompt",
            "role": "The Anatomical Mentor",
            "source_hash": "abc123",
            "modules": ["Upper Limb", "Thorax"],
        })

        self.assertEqual(tree["title"], "Anatomy")
        self.assertEqual(tree["input_type"], "system_prompt")
        self.assertEqual(len(tree["modules"]), 2)
        self.assertFalse(tree["modules"][0]["locked"])
        self.assertTrue(tree["modules"][1]["locked"])
        self.assertEqual(tree["modules"][0]["nodes"][0]["title"], "Upper Limb Overview")

    def test_create_track_uses_overview_when_modules_missing(self):
        tree = create_track_from_spec(self.session, {"track_title": "Scratch"})
        self.assertEqual([m["title"] for m in tree["modules"]], ["Overview"])

    def test_list_and_get_track_tree(self):
        created = create_track_from_spec(self.session, {
            "track_title": "Python",
            "modules": ["Variables"],
        })
        summaries = list_tracks(self.session)
        fetched = get_track_tree(self.session, created["id"])

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["title"], "Python")
        self.assertEqual(fetched["modules"][0]["title"], "Variables")

    def test_get_or_create_lesson_for_node_builds_starter_blocks(self):
        tree = create_track_from_spec(self.session, {
            "track_title": "Anatomy",
            "modules": ["Upper Limb"],
        })
        node_id = tree["modules"][0]["nodes"][0]["id"]

        lesson = get_or_create_lesson_for_node(self.session, node_id)

        self.assertEqual(lesson["node_id"], node_id)
        self.assertEqual(lesson["title"], "Upper Limb Overview")
        self.assertEqual([b["block_type"] for b in lesson["blocks"]], ["text", "recall_prompt"])

    def test_add_lesson_block_appends_safe_payload(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Variables"]})
        node_id = tree["modules"][0]["nodes"][0]["id"]
        lesson = get_or_create_lesson_for_node(self.session, node_id)

        updated = add_lesson_block(self.session, lesson["id"], {
            "block_type": "definition",
            "title": "Variable",
            "payload": {"term": "variable", "body": "A named reference to a value."},
            "source_refs": ["manual:1"],
            "confidence": 0.9,
        })

        self.assertEqual(len(updated["blocks"]), 3)
        self.assertEqual(updated["blocks"][-1]["block_type"], "definition")
        self.assertEqual(updated["blocks"][-1]["payload"]["term"], "variable")
        self.assertEqual(get_lesson_tree(self.session, lesson["id"])["blocks"][-1]["source_refs"], ["manual:1"])

    def test_add_lesson_block_rejects_unknown_type(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Variables"]})
        node_id = tree["modules"][0]["nodes"][0]["id"]
        lesson = get_or_create_lesson_for_node(self.session, node_id)

        with self.assertRaises(ValueError):
            add_lesson_block(self.session, lesson["id"], {"block_type": "raw_html", "payload": {}})


if __name__ == "__main__":
    unittest.main()
