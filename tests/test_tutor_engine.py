import json
import unittest
from unittest.mock import MagicMock, patch

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import create_track_from_spec
from app.sandbox_client import SandboxResult
from app.tutor_engine import MAX_TOOL_ROUNDS, build_chat_messages, generate_tutor_prompt, run_tutor_turn
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

    def test_build_chat_messages_replays_a_prior_tool_round_trip(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        add_message(self.session, self.track["id"], "user", "what's 1+1?")
        tool_calls = [{"function": {"name": "run_python", "arguments": {"code": "print(1+1)"}}}]
        add_message(self.session, self.track["id"], "assistant", "",
                    tool_calls_json=json.dumps(tool_calls))
        add_message(self.session, self.track["id"], "tool", "stdout:\n2\nexit_code: 0", tool_name="run_python")
        add_message(self.session, self.track["id"], "assistant", "It's 2.")

        with patch("app.rag_engine.search_track", return_value=[]):
            messages = build_chat_messages(self.session, self.track["id"], "and 2+2?")

        roles = [m["role"] for m in messages]
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "assistant", "user"])
        tool_call_msg = messages[2]
        self.assertEqual(tool_call_msg["tool_calls"], tool_calls)
        self.assertEqual(messages[3]["content"], "stdout:\n2\nexit_code: 0")

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

    # ---- run_tutor_turn: tool-calling (Phase 3) ----

    def test_run_tutor_turn_calls_run_python_and_continues_with_the_result(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        tool_calls = [{"function": {"name": "run_python", "arguments": {"code": "print(1+1)"}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "The answer is 2."}, "done": True}])

        sandbox = MagicMock()
        sandbox.run.return_value = SandboxResult(stdout="2\n", stderr="", exit_code=0, timed_out=False)

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox):
            events = list(run_tutor_turn(self.track["id"], "what's 1+1?"))

        tool_call_events = [e for e in events if e["type"] == "tool_call"]
        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        self.assertEqual(len(tool_call_events), 1)
        self.assertEqual(tool_call_events[0]["name"], "run_python")
        self.assertEqual(tool_call_events[0]["args"], {"code": "print(1+1)"})
        self.assertEqual(len(tool_result_events), 1)
        self.assertEqual(tool_result_events[0]["stdout"], "2\n")
        self.assertEqual(tool_result_events[0]["exit_code"], 0)
        sandbox.run.assert_called_once_with("print(1+1)", timeout_s=10)

        text = "".join(e["content"] for e in events if e["type"] == "text_delta")
        self.assertEqual(text, "The answer is 2.")

        from app.tutor_store import list_messages
        history = list_messages(self.session, self.track["id"])
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "tool", "assistant"])
        self.assertIsNotNone(history[1]["tool_calls_json"])
        self.assertEqual(history[2]["tool_name"], "run_python")
        self.assertIn("2\n", history[2]["content"])
        self.assertEqual(history[3]["content"], "The answer is 2.")

    def test_run_tutor_turn_stops_at_the_round_cap_instead_of_looping_forever(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        tool_calls = [{"function": {"name": "run_python", "arguments": {"code": "1"}}}]
        # a model that keeps asking to call a tool no matter how many rounds pass
        rounds = [iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
                  for _ in range(MAX_TOOL_ROUNDS + 1)]

        sandbox = MagicMock()
        sandbox.run.return_value = SandboxResult(stdout="1\n", stderr="", exit_code=0, timed_out=False)

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=rounds), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox):
            events = list(run_tutor_turn(self.track["id"], "loop forever?"))

        self.assertEqual(sandbox.run.call_count, MAX_TOOL_ROUNDS + 1)
        final_text = "".join(e["content"] for e in events if e["type"] == "text_delta")
        self.assertIn("Stopped after several tool calls", final_text)

        from app.tutor_store import list_messages
        history = list_messages(self.session, self.track["id"])
        self.assertEqual(history[-1]["role"], "assistant")
        self.assertIn("Stopped after several tool calls", history[-1]["content"])

    def test_run_tutor_turn_reports_an_unknown_tool_without_crashing_the_turn(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        tool_calls = [{"function": {"name": "mystery_tool", "arguments": {}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "never mind."}, "done": True}])

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]):
            events = list(run_tutor_turn(self.track["id"], "use a tool I made up"))

        result = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("unknown tool", result["stderr"])
        text = "".join(e["content"] for e in events if e["type"] == "text_delta")
        self.assertEqual(text, "never mind.")

    def test_run_tutor_turn_parses_string_encoded_tool_arguments(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        tool_calls = [{"function": {"name": "run_python", "arguments": json.dumps({"code": "print(42)"})}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "42."}, "done": True}])

        sandbox = MagicMock()
        sandbox.run.return_value = SandboxResult(stdout="42\n", stderr="", exit_code=0, timed_out=False)

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox):
            events = list(run_tutor_turn(self.track["id"], "what's the answer?"))

        sandbox.run.assert_called_once_with("print(42)", timeout_s=10)
        tool_call_event = next(e for e in events if e["type"] == "tool_call")
        self.assertEqual(tool_call_event["args"], {"code": "print(42)"})


if __name__ == "__main__":
    unittest.main()
