import unittest
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import create_track_from_spec
from app.tutor_engine import build_chat_messages, generate_tutor_prompt, run_tutor_turn
from app.tutor_store import add_message, enable_tutor


class TestTutorEngine(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.track = create_track_from_spec(self.session, {"track_title": "Robotics", "modules": ["Kinematics"]})

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    # ---- generate_tutor_prompt ----

    def test_generate_tutor_prompt_requires_description(self):
        with self.assertRaises(ValueError):
            generate_tutor_prompt("   ")

    def test_generate_tutor_prompt_delegates_to_generate_text(self):
        with patch("app.generation_client.generate_text", return_value="  A direct robotics tutor.  ") as mock_gen:
            result = generate_tutor_prompt("direct, teaches ROS2")
        mock_gen.assert_called_once()
        self.assertEqual(mock_gen.call_args.args[1], "direct, teaches ROS2")
        self.assertEqual(result, "A direct robotics tutor.")

    # ---- build_chat_messages ----

    def test_build_chat_messages_returns_none_when_tutor_not_configured(self):
        with patch("app.rag_engine.search_track", return_value=[]):
            self.assertIsNone(build_chat_messages(self.session, 999, "hi"))

    def test_build_chat_messages_includes_system_prompt_history_and_user_turn(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        add_message(self.session, self.track["id"], "user", "earlier question")
        add_message(self.session, self.track["id"], "assistant", "earlier answer")

        with patch("app.rag_engine.search_track", return_value=[]):
            messages = build_chat_messages(self.session, self.track["id"], "new question")

        self.assertEqual(messages[0], {"role": "system", "content": "You are a robotics tutor."})
        self.assertEqual(messages[1], {"role": "user", "content": "earlier question"})
        self.assertEqual(messages[2], {"role": "assistant", "content": "earlier answer"})
        self.assertEqual(messages[-1], {"role": "user", "content": "new question"})

    def test_build_chat_messages_injects_rag_context_turn_when_hits_found(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        hits = [{"source_title": "ROS2 Notes", "heading": "Topics", "snippet": "A topic is a named bus."}]

        with patch("app.rag_engine.search_track", return_value=hits):
            messages = build_chat_messages(self.session, self.track["id"], "what is a topic?")

        rag_turns = [m for m in messages if m["role"] == "system" and "ROS2 Notes" in m["content"]]
        self.assertEqual(len(rag_turns), 1)
        # RAG turn comes after history/system prompt but before the final user turn.
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-2], rag_turns[0])

    def test_build_chat_messages_omits_rag_turn_when_no_hits(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        with patch("app.rag_engine.search_track", return_value=[]):
            messages = build_chat_messages(self.session, self.track["id"], "hello")
        self.assertEqual(len(messages), 2)  # system + user only

    # ---- run_tutor_turn ----

    def test_run_tutor_turn_yields_error_when_tutor_not_enabled(self):
        with patch("app.db.engine", self.engine):
            events = list(run_tutor_turn(self.track["id"], "hello"))
        self.assertEqual(events, [{"type": "error", "content": "tutor_not_enabled"}])

    def test_run_tutor_turn_streams_deltas_and_persists_both_messages(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        chunks = [
            {"message": {"content": "Hel"}, "done": False},
            {"message": {"content": "lo!"}, "done": False},
            {"message": {"content": ""}, "done": True},
        ]

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", return_value=iter(chunks)), \
             patch("app.rag_engine.search_track", return_value=[]):
            events = list(run_tutor_turn(self.track["id"], "hi there"))

        text_events = [e for e in events if e["type"] == "text_delta"]
        self.assertEqual("".join(e["content"] for e in text_events), "Hello!")

        from app.tutor_store import list_messages
        history = list_messages(self.session, self.track["id"])
        self.assertEqual([(m["role"], m["content"]) for m in history],
                          [("user", "hi there"), ("assistant", "Hello!")])

    def test_run_tutor_turn_surfaces_stream_error_without_persisting_empty_reply(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        chunks = [{"error": "ollama unreachable"}]

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", return_value=iter(chunks)), \
             patch("app.rag_engine.search_track", return_value=[]):
            events = list(run_tutor_turn(self.track["id"], "hi there"))

        self.assertIn({"type": "error", "content": "ollama unreachable"}, events)
        from app.tutor_store import list_messages
        history = list_messages(self.session, self.track["id"])
        # user turn still recorded, no assistant turn since nothing was generated
        self.assertEqual([m["role"] for m in history], ["user"])


if __name__ == "__main__":
    unittest.main()
