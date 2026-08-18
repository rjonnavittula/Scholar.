import unittest
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine

from app.chunk_store import create_source_chunk
from app.learn_store import create_track_from_spec, get_lesson_tree, get_or_create_lesson_for_node
from app.models import LearningNode
from app.rag_engine import _validate_blocks, gather_context, generate_lesson_blocks, search_track
from app.source_store import create_source, link_source_to_track


class TestRagEngine(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _first_node_id(self, tree):
        return tree["modules"][0]["nodes"][0]["id"]

    def test_gather_context_returns_empty_without_linked_sources(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics"]})
        node = self.session.get(LearningNode, self._first_node_id(tree))
        context = gather_context(self.session, node)
        self.assertEqual(context["chunks"], [])

    def test_gather_context_falls_back_to_chunk_order_without_search_hits(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Notes", "source_type": "text", "body_text": "x"})
        link_source_to_track(self.session, tree["id"], source["id"], "primary")
        create_source_chunk(self.session, {"source_id": source["id"], "position": 1, "heading": "Intro", "body_text": "First chunk"})
        create_source_chunk(self.session, {"source_id": source["id"], "position": 2, "heading": "More", "body_text": "Second chunk"})

        node = self.session.get(LearningNode, self._first_node_id(tree))
        with patch("app.vector_store.search_chunks", return_value=[]):
            context = gather_context(self.session, node)

        self.assertEqual(len(context["chunks"]), 2)
        self.assertEqual(context["chunks"][0]["heading"], "Intro")

    def test_generate_lesson_blocks_reports_no_sources(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics"]})
        node_id = self._first_node_id(tree)
        result = generate_lesson_blocks(self.session, node_id)
        self.assertEqual(result["generation"]["status"], "no_sources")

    def test_generate_lesson_blocks_replaces_blocks_on_success(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics"]})
        node_id = self._first_node_id(tree)
        source = create_source(self.session, {"title": "Notes", "source_type": "text", "body_text": "x"})
        link_source_to_track(self.session, tree["id"], source["id"], "primary")
        create_source_chunk(self.session, {"source_id": source["id"], "position": 1, "heading": "Intro", "body_text": "Variables store references."})

        generated = {"blocks": [
            {"block_type": "definition", "title": "Variables", "payload": {"term": "variable", "definition": "a name bound to a value"}, "source_refs": [1], "confidence": 0.8},
            {"block_type": "quiz", "title": "Check", "payload": {"question": "What is a variable?", "options": ["a name bound to a value", "a loop"], "correct_index": 0}, "source_refs": [1], "confidence": 0.7},
            {"block_type": "recall_prompt", "title": "Recall", "payload": {"prompt": "Explain variables."}, "source_refs": [], "confidence": 0.5},
        ]}

        with patch("app.vector_store.search_chunks", return_value=[]), \
             patch("app.generation_client.generate_json", return_value=generated):
            result = generate_lesson_blocks(self.session, node_id)

        self.assertEqual(result["generation"]["status"], "generated")
        block_types = [b["block_type"] for b in result["lesson"]["blocks"]]
        self.assertEqual(block_types, ["definition", "quiz", "recall_prompt"])
        self.assertEqual(result["lesson"]["status"], "generated")

    def test_generate_lesson_blocks_keeps_starter_blocks_when_generation_unavailable(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics"]})
        node_id = self._first_node_id(tree)
        source = create_source(self.session, {"title": "Notes", "source_type": "text", "body_text": "x"})
        link_source_to_track(self.session, tree["id"], source["id"], "primary")
        create_source_chunk(self.session, {"source_id": source["id"], "position": 1, "heading": "Intro", "body_text": "Variables store references."})

        with patch("app.vector_store.search_chunks", return_value=[]), \
             patch("app.generation_client.generate_json", side_effect=RuntimeError("ollama down")):
            result = generate_lesson_blocks(self.session, node_id)

        self.assertEqual(result["generation"]["status"], "unavailable")
        lesson = get_lesson_tree(self.session, result["lesson"]["id"])
        self.assertEqual(lesson["status"], "draft")
        self.assertEqual(len(lesson["blocks"]), 2)

    def test_generate_lesson_blocks_returns_none_for_missing_node(self):
        self.assertIsNone(generate_lesson_blocks(self.session, 999))

    def test_validate_blocks_drops_invalid_quiz_and_synthesizes_recall(self):
        raw = [
            {"block_type": "text", "payload": {"body": "hi"}},
            {"block_type": "quiz", "payload": {"options": ["a"], "correct_index": 0}},
            {"block_type": "nonsense", "payload": {}},
        ]
        cleaned = _validate_blocks(raw, "Topic")
        types = [b["block_type"] for b in cleaned]
        self.assertEqual(types, ["text", "recall_prompt"])

    def test_validate_blocks_returns_empty_for_non_list(self):
        self.assertEqual(_validate_blocks(None, "Topic"), [])

    def test_validate_blocks_drops_ordered_relation_without_items(self):
        raw = [{"block_type": "ordered_relation", "payload": {"items": ["only one"]}}]
        self.assertEqual(_validate_blocks(raw, "Topic"), [])

    def test_validate_blocks_keeps_valid_ordered_relation(self):
        raw = [{"block_type": "ordered_relation", "payload": {"prompt": "Order these", "items": ["first", "second"]}}]
        cleaned = _validate_blocks(raw, "Topic")
        types = [b["block_type"] for b in cleaned]
        self.assertIn("ordered_relation", types)

    def test_search_track_returns_empty_without_linked_sources(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics"]})
        self.assertEqual(search_track(self.session, tree["id"], "variables"), [])

    def test_search_track_returns_empty_for_blank_query(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Notes", "source_type": "text", "body_text": "x"})
        link_source_to_track(self.session, tree["id"], source["id"], "primary")
        self.assertEqual(search_track(self.session, tree["id"], "   "), [])

    def test_search_track_maps_hits_to_chunk_details(self):
        tree = create_track_from_spec(self.session, {"track_title": "Python Course", "modules": ["Basics"]})
        source = create_source(self.session, {"title": "Notes", "source_type": "text", "body_text": "x"})
        link_source_to_track(self.session, tree["id"], source["id"], "primary")
        chunk = create_source_chunk(self.session, {"source_id": source["id"], "position": 1, "heading": "Intro", "body_text": "Variables store references."})

        with patch("app.vector_store.search_chunks", return_value=[{"chunk_id": chunk["id"], "source_id": source["id"], "score": 0.9}]):
            results = search_track(self.session, tree["id"], "what is a variable")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["heading"], "Intro")
        self.assertEqual(results[0]["source_title"], "Notes")
        self.assertEqual(results[0]["score"], 0.9)


if __name__ == "__main__":
    unittest.main()
