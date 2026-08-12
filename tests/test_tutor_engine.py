import json
import unittest
from unittest.mock import MagicMock, patch

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import create_track_from_spec
from app.sandbox_client import SandboxResult
from app.tutor_engine import (
    MAX_TOOL_ROUNDS, build_chat_messages, generate_tutor_prompt, regenerate_tutor_turn, run_tutor_turn,
)
from app.tutor_store import add_message, enable_tutor, list_messages


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

    def test_build_chat_messages_with_none_appends_nothing_and_queries_rag_with_the_last_user_turn(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        add_message(self.session, self.track["id"], "user", "what is torque?")

        with patch("app.rag_engine.search_track", return_value=[]) as mock_search:
            messages = build_chat_messages(self.session, self.track["id"], None)

        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertEqual(messages[-1]["content"], "what is torque?")
        mock_search.assert_called_once()
        self.assertEqual(mock_search.call_args.args[2], "what is torque?")

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

    # ---- run_tutor_turn: dynamic tool authoring (Phase 4) ----

    def test_tools_for_track_includes_base_tools_plus_stored_dynamic_tools(self):
        from app.tutor_engine import _tools_for_track
        from app.tutor_store import upsert_dynamic_tool

        upsert_dynamic_tool(
            self.session, self.track["id"], "double", "doubles a number",
            "def double(n):\n    return n * 2",
            json.dumps({"type": "object", "properties": {"n": {"type": "number"}}, "required": ["n"]}),
        )

        tools = _tools_for_track(self.session, self.track["id"])
        names = [t["function"]["name"] for t in tools]
        self.assertIn("run_python", names)
        self.assertIn("define_tool", names)
        self.assertIn("double", names)

        double_tool = next(t for t in tools if t["function"]["name"] == "double")
        self.assertEqual(double_tool["function"]["description"], "doubles a number")
        self.assertEqual(double_tool["function"]["parameters"]["properties"]["n"]["type"], "number")

    def test_run_tutor_turn_defines_a_tool_then_calls_it_in_a_later_round(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        define_args = {
            "name": "c_to_f",
            "description": "Convert Celsius to Fahrenheit.",
            "parameters_schema": json.dumps(
                {"type": "object", "properties": {"c": {"type": "number"}}, "required": ["c"]}
            ),
            "code": "def c_to_f(c):\n    return c * 9 / 5 + 32",
        }
        define_call = [{"function": {"name": "define_tool", "arguments": define_args}}]
        use_call = [{"function": {"name": "c_to_f", "arguments": {"c": 100}}}]

        round1 = iter([{"message": {"content": "", "tool_calls": define_call}, "done": True}])
        round2 = iter([{"message": {"content": "", "tool_calls": use_call}, "done": True}])
        round3 = iter([{"message": {"content": "100C is 212F."}, "done": True}])

        sandbox = MagicMock()
        # 1st sandbox.run: define_tool's smoke test (just loading the def).
        # 2nd sandbox.run: the actual composed call to the new tool.
        sandbox.run.side_effect = [
            SandboxResult(stdout="", stderr="", exit_code=0, timed_out=False),
            SandboxResult(stdout="212.0\n", stderr="", exit_code=0, timed_out=False),
        ]

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2, round3]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox):
            events = list(run_tutor_turn(self.track["id"], "define and use a celsius to fahrenheit tool"))

        self.assertEqual(sandbox.run.call_count, 2)
        smoke_code = sandbox.run.call_args_list[0].args[0]
        self.assertIn("def c_to_f", smoke_code)
        call_code = sandbox.run.call_args_list[1].args[0]
        self.assertIn("c_to_f(**{'c': 100})", call_code)

        from app.tutor_store import list_dynamic_tools
        stored = list_dynamic_tools(self.session, self.track["id"])
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["name"], "c_to_f")

        text = "".join(e["content"] for e in events if e["type"] == "text_delta")
        self.assertEqual(text, "100C is 212F.")

    def test_run_tutor_turn_define_tool_syntax_error_is_reported_and_not_stored(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        define_args = {
            "name": "broken",
            "description": "broken on purpose",
            "parameters_schema": "{}",
            "code": "this is not valid python(",
        }
        define_call = [{"function": {"name": "define_tool", "arguments": define_args}}]
        round1 = iter([{"message": {"content": "", "tool_calls": define_call}, "done": True}])
        round2 = iter([{"message": {"content": "let me fix that."}, "done": True}])

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]):
            events = list(run_tutor_turn(self.track["id"], "define a broken tool"))

        result = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("syntax error", result["stderr"])

        from app.tutor_store import list_dynamic_tools
        self.assertEqual(list_dynamic_tools(self.session, self.track["id"]), [])

    def test_run_tutor_turn_define_tool_redefine_upserts_instead_of_duplicating(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        first_args = {"name": "half", "description": "halves a number", "parameters_schema": "{}",
                       "code": "def half(n):\n    return n / 2"}
        second_args = {"name": "half", "description": "halves a number (fixed)", "parameters_schema": "{}",
                        "code": "def half(n):\n    return float(n) / 2"}
        round1 = iter([{"message": {"content": "", "tool_calls":
                        [{"function": {"name": "define_tool", "arguments": first_args}}]}, "done": True}])
        round2 = iter([{"message": {"content": "", "tool_calls":
                        [{"function": {"name": "define_tool", "arguments": second_args}}]}, "done": True}])
        round3 = iter([{"message": {"content": "done."}, "done": True}])

        sandbox = MagicMock()
        sandbox.run.return_value = SandboxResult(stdout="", stderr="", exit_code=0, timed_out=False)

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2, round3]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox):
            list(run_tutor_turn(self.track["id"], "define half, then redefine it"))

        from app.tutor_store import list_dynamic_tools
        stored = list_dynamic_tools(self.session, self.track["id"])
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["description"], "halves a number (fixed)")

    # ---- run_tutor_turn: render_plot (Phase 4 Part B) ----

    def test_run_tutor_turn_render_plot_saves_media_and_persists_a_url_reference(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        plot_code = "import matplotlib.pyplot as plt\nplt.plot([1,2,3])\nplt.savefig('/tmp/output.png')"
        tool_calls = [{"function": {"name": "render_plot", "arguments": {"code": plot_code}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "Here's the plot."}, "done": True}])

        sandbox = MagicMock()
        sandbox.run.return_value = SandboxResult(
            stdout="", stderr="", exit_code=0, timed_out=False,
            media_kind="image/png", media_base64="aGVsbG8=",
        )

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox), \
             patch("app.media_store.save_media", return_value="/learn/tutor/media/abc123.png") as mock_save:
            events = list(run_tutor_turn(self.track["id"], "plot y=x"))

        sandbox.run.assert_called_once_with(plot_code, timeout_s=15, capture_media=True)
        mock_save.assert_called_once_with(self.track["id"], "image/png", b"hello")

        result_event = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result_event["media_url"], "/learn/tutor/media/abc123.png")
        self.assertEqual(result_event["media_kind"], "image/png")

        from app.tutor_store import list_messages
        history = list_messages(self.session, self.track["id"])
        tool_msg = next(m for m in history if m["role"] == "tool")
        self.assertIn("/learn/tutor/media/abc123.png", tool_msg["content"])

    def test_run_tutor_turn_render_plot_without_savefig_reports_no_image_produced(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        tool_calls = [{"function": {"name": "render_plot", "arguments": {"code": "print('oops, forgot savefig')"}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "let me fix that."}, "done": True}])

        sandbox = MagicMock()
        sandbox.run.return_value = SandboxResult(stdout="oops, forgot savefig\n", stderr="", exit_code=0, timed_out=False)

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox):
            events = list(run_tutor_turn(self.track["id"], "plot something"))

        result_event = next(e for e in events if e["type"] == "tool_result")
        self.assertNotIn("media_url", result_event)
        self.assertEqual(result_event["exit_code"], 0)

    # ---- run_tutor_turn: render_animation (Phase 4 Part C) ----

    def test_run_tutor_turn_render_animation_saves_a_video_and_persists_a_url_reference(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        manim_code = "from manim import *\nclass MyScene(Scene):\n    def construct(self):\n        pass"
        tool_calls = [{"function": {"name": "render_animation",
                                     "arguments": {"manim_code": manim_code, "scene_name": "MyScene"}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "Here's the animation."}, "done": True}])

        sandbox = MagicMock()
        sandbox.run.return_value = SandboxResult(
            stdout="", stderr="", exit_code=0, timed_out=False,
            media_kind="video/mp4", media_base64="aGVsbG8=",
        )

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox), \
             patch("app.media_store.save_media", return_value="/learn/tutor/media/abc123.mp4") as mock_save:
            events = list(run_tutor_turn(self.track["id"], "animate something"))

        sandbox.run.assert_called_once_with(manim_code, timeout_s=90, capture_video=True, scene_name="MyScene")
        mock_save.assert_called_once_with(self.track["id"], "video/mp4", b"hello")

        result_event = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result_event["media_url"], "/learn/tutor/media/abc123.mp4")
        self.assertEqual(result_event["media_kind"], "video/mp4")

        from app.tutor_store import list_messages
        history = list_messages(self.session, self.track["id"])
        tool_msg = next(m for m in history if m["role"] == "tool")
        self.assertIn("/learn/tutor/media/abc123.mp4", tool_msg["content"])

    def test_run_tutor_turn_render_animation_requires_manim_code_and_scene_name(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        tool_calls = [{"function": {"name": "render_animation", "arguments": {"manim_code": "from manim import *"}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "let me fix that."}, "done": True}])

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]):
            events = list(run_tutor_turn(self.track["id"], "animate without a scene name"))

        result_event = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result_event["exit_code"], 1)
        self.assertIn("scene_name", result_event["stderr"])

    # ---- run_tutor_turn: render_interactive (Phase 4 Part C) ----

    def test_run_tutor_turn_render_interactive_saves_html_and_persists_a_url_reference(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        html = "<!doctype html><html><body><button onclick=\"alert(1)\">go</button></body></html>"
        tool_calls = [{"function": {"name": "render_interactive", "arguments": {"html": html}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "Here's an interactive demo."}, "done": True}])

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.media_store.save_media", return_value="/learn/tutor/media/xyz789.html") as mock_save:
            events = list(run_tutor_turn(self.track["id"], "show me something interactive"))

        mock_save.assert_called_once_with(self.track["id"], "text/html", html.encode("utf-8"))
        result_event = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result_event["media_url"], "/learn/tutor/media/xyz789.html")
        self.assertEqual(result_event["media_kind"], "text/html")

    def test_run_tutor_turn_render_interactive_rejects_empty_html(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        tool_calls = [{"function": {"name": "render_interactive", "arguments": {"html": "   "}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "let me fix that."}, "done": True}])

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]):
            events = list(run_tutor_turn(self.track["id"], "show me nothing"))

        result_event = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result_event["exit_code"], 1)
        self.assertIn("no html provided", result_event["stderr"])

    def test_run_tutor_turn_render_interactive_rejects_oversized_html(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        from app.tutor_engine import MAX_INTERACTIVE_HTML_BYTES
        huge_html = "<html>" + ("x" * (MAX_INTERACTIVE_HTML_BYTES + 1)) + "</html>"
        tool_calls = [{"function": {"name": "render_interactive", "arguments": {"html": huge_html}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "too big."}, "done": True}])

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]):
            events = list(run_tutor_turn(self.track["id"], "show me something huge"))

        result_event = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result_event["exit_code"], 1)
        self.assertIn("too large", result_event["stderr"])

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

    # ---- regenerate_tutor_turn ----

    def test_regenerate_tutor_turn_yields_error_when_tutor_not_enabled(self):
        with patch("app.db.engine", self.engine):
            events = list(regenerate_tutor_turn(self.track["id"]))
        self.assertEqual(events, [{"type": "error", "content": "tutor_not_enabled"}])

    def test_regenerate_tutor_turn_yields_error_when_nothing_to_regenerate(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        with patch("app.db.engine", self.engine):
            events = list(regenerate_tutor_turn(self.track["id"]))
        self.assertEqual(events, [{"type": "error", "content": "nothing_to_regenerate"}])

    def test_regenerate_tutor_turn_removes_the_old_reply_and_streams_a_new_one(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        add_message(self.session, self.track["id"], "user", "what's the capital of France?")
        add_message(self.session, self.track["id"], "assistant", "London.")  # the "wrong" reply to regenerate away

        chunks = iter([{"message": {"content": "Paris."}, "done": True}])

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", return_value=chunks) as mock_stream, \
             patch("app.rag_engine.search_track", return_value=[]):
            events = list(regenerate_tutor_turn(self.track["id"]))

        text = "".join(e["content"] for e in events if e["type"] == "text_delta")
        self.assertEqual(text, "Paris.")

        # the model saw the question once, as history's trailing user turn -
        # not duplicated by build_chat_messages appending it again.
        sent_messages = mock_stream.call_args.args[0]
        user_turns = [m for m in sent_messages if m["role"] == "user"]
        self.assertEqual(len(user_turns), 1)
        self.assertEqual(user_turns[0]["content"], "what's the capital of France?")

        history = list_messages(self.session, self.track["id"])
        self.assertEqual([(m["role"], m["content"]) for m in history],
                          [("user", "what's the capital of France?"), ("assistant", "Paris.")])

    def test_regenerate_tutor_turn_can_call_tools_the_same_as_a_normal_turn(self):
        enable_tutor(self.session, self.track["id"], "You are a robotics tutor.")
        add_message(self.session, self.track["id"], "user", "what's 6*7?")
        add_message(self.session, self.track["id"], "assistant", "41.")  # wrong, regenerate should fix it

        tool_calls = [{"function": {"name": "run_python", "arguments": {"code": "print(6*7)"}}}]
        round1 = iter([{"message": {"content": "", "tool_calls": tool_calls}, "done": True}])
        round2 = iter([{"message": {"content": "42."}, "done": True}])

        sandbox = MagicMock()
        sandbox.run.return_value = SandboxResult(stdout="42\n", stderr="", exit_code=0, timed_out=False)

        with patch("app.db.engine", self.engine), \
             patch("app.generation_client.stream_chat", side_effect=[round1, round2]), \
             patch("app.rag_engine.search_track", return_value=[]), \
             patch("app.sandbox_client.get_sandbox_provider", return_value=sandbox):
            events = list(regenerate_tutor_turn(self.track["id"]))

        text = "".join(e["content"] for e in events if e["type"] == "text_delta")
        self.assertEqual(text, "42.")
        history = list_messages(self.session, self.track["id"])
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "tool", "assistant"])


if __name__ == "__main__":
    unittest.main()
