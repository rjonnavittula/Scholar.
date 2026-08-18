import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import (
    add_lesson_block, complete_learning_node, create_track_from_spec, delete_track,
    get_lesson_tree, get_or_create_lesson_for_node, get_track_tree, list_tracks,
    start_learning_node,
)


class TestLearnStore(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

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


    def test_create_track_reuses_duplicate_source_hash(self):
        first = create_track_from_spec(self.session, {
            "track_title": "Python Course",
            "source_hash": "same-source",
            "modules": ["Basics", "Functions"],
        })
        second = create_track_from_spec(self.session, {
            "track_title": "Python Course",
            "source_hash": "same-source",
            "modules": ["Basics", "Functions"],
        })

        self.assertEqual(second["id"], first["id"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual(len(list_tracks(self.session)), 1)

    def test_create_track_reuses_duplicate_title_and_modules_without_hash(self):
        first = create_track_from_spec(self.session, {
            "track_title": "Python Course",
            "modules": ["Basics", "Functions"],
        })
        second = create_track_from_spec(self.session, {
            "track_title": "python course",
            "modules": ["Basics", "Functions"],
        })

        self.assertEqual(second["id"], first["id"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual(len(list_tracks(self.session)), 1)

    def test_list_and_get_track_tree(self):
        created = create_track_from_spec(self.session, {
            "track_title": "Python",
            "modules": ["Variables"],
        })
        summaries = list_tracks(self.session)
        fetched = get_track_tree(self.session, created["id"])

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["title"], "Python")
        self.assertEqual(summaries[0]["module_titles"], ["Variables"])
        self.assertEqual(fetched["modules"][0]["title"], "Variables")


    def test_list_tracks_includes_progress_summary(self):
        tree = create_track_from_spec(self.session, {
            "track_title": "Python",
            "modules": ["Basics", "Functions"],
        })
        node_id = tree["modules"][0]["nodes"][0]["id"]

        complete_learning_node(self.session, node_id, mastery=1.0)
        summary = list_tracks(self.session)[0]

        self.assertEqual(summary["module_count"], 2)
        self.assertEqual(summary["completed_module_count"], 1)
        self.assertAlmostEqual(summary["mastery"], 0.5)
        self.assertEqual(summary["next_module_title"], "Functions")

    def test_delete_track_removes_learning_tree(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        node_id = tree["modules"][0]["nodes"][0]["id"]
        lesson = get_or_create_lesson_for_node(self.session, node_id)
        add_lesson_block(self.session, lesson["id"], {"block_type": "definition", "payload": {"body": "x"}})

        self.assertTrue(delete_track(self.session, tree["id"]))
        self.assertIsNone(get_track_tree(self.session, tree["id"]))
        self.assertEqual(list_tracks(self.session), [])
        self.assertFalse(delete_track(self.session, tree["id"]))

    def test_delete_track_with_linked_source_does_not_violate_fk(self):
        from app.source_store import create_source, link_source_to_track

        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Notes", "source_type": "text", "body_text": "x"})
        link_source_to_track(self.session, tree["id"], source["id"], "primary")

        self.assertTrue(delete_track(self.session, tree["id"]))
        self.assertIsNone(get_track_tree(self.session, tree["id"]))

    def test_delete_track_with_tutor_messages_does_not_violate_fk(self):
        from app.tutor_store import add_message, enable_tutor

        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        enable_tutor(self.session, tree["id"], "You are a tutor.")
        add_message(self.session, tree["id"], "user", "hello")
        add_message(self.session, tree["id"], "assistant", "hi there")

        self.assertTrue(delete_track(self.session, tree["id"]))
        self.assertIsNone(get_track_tree(self.session, tree["id"]))

    def test_delete_track_with_dynamic_tools_does_not_violate_fk(self):
        from app.tutor_store import enable_tutor, upsert_dynamic_tool

        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        enable_tutor(self.session, tree["id"], "You are a tutor.")
        upsert_dynamic_tool(self.session, tree["id"], "double", "doubles a number",
                             "def double(n):\n    return n * 2", "{}")

        self.assertTrue(delete_track(self.session, tree["id"]))
        self.assertIsNone(get_track_tree(self.session, tree["id"]))

    def test_delete_track_removes_its_saved_media_files(self):
        from unittest.mock import patch

        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})

        with patch("app.media_store.delete_media_for_track") as mock_delete:
            self.assertTrue(delete_track(self.session, tree["id"]))
        mock_delete.assert_called_once_with(tree["id"])

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
        self.assertIn("Start here", lesson["blocks"][0]["payload"]["body"])

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


    def test_start_learning_node_marks_lesson_and_track_active(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        node_id = tree["modules"][0]["nodes"][0]["id"]

        result = start_learning_node(self.session, node_id)

        self.assertEqual(result["lesson"]["status"], "in_progress")
        self.assertEqual(result["track"]["status"], "active")
        self.assertFalse(result["track"]["modules"][0]["completed"])

    def test_complete_learning_node_marks_progress_and_unlocks_next_module(self):
        tree = create_track_from_spec(self.session, {
            "track_title": "Python",
            "modules": ["Basics", "Functions"],
        })
        node_id = tree["modules"][0]["nodes"][0]["id"]

        result = complete_learning_node(self.session, node_id, mastery=0.8)

        first = result["track"]["modules"][0]
        second = result["track"]["modules"][1]
        self.assertEqual(result["lesson"]["status"], "completed")
        self.assertTrue(first["completed"])
        self.assertAlmostEqual(first["mastery"], 0.8)
        self.assertFalse(second["locked"])
        self.assertFalse(second["nodes"][0]["locked"])
        self.assertEqual(result["track"]["status"], "active")

    def test_complete_learning_node_clamps_mastery(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Basics"]})
        node_id = tree["modules"][0]["nodes"][0]["id"]

        result = complete_learning_node(self.session, node_id, mastery=3.5)

        self.assertEqual(result["track"]["modules"][0]["nodes"][0]["mastery"], 1.0)
        self.assertEqual(result["track"]["status"], "completed")

    def test_add_lesson_block_rejects_unknown_type(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python", "modules": ["Variables"]})
        node_id = tree["modules"][0]["nodes"][0]["id"]
        lesson = get_or_create_lesson_for_node(self.session, node_id)

        with self.assertRaises(ValueError):
            add_lesson_block(self.session, lesson["id"], {"block_type": "raw_html", "payload": {}})


if __name__ == "__main__":
    unittest.main()
