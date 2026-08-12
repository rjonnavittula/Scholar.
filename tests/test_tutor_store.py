import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import create_track_from_spec
from app.tutor_store import (
    add_message, clear_messages, disable_tutor, enable_tutor, get_tutor_config, list_messages,
    truncate_after_last_user_message,
)


class TestTutorStore(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.track = create_track_from_spec(self.session, {"track_title": "Anatomy", "modules": ["Skeletal System"]})

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_track_starts_with_tutor_disabled(self):
        config = get_tutor_config(self.session, self.track["id"])
        self.assertFalse(config["tutor_enabled"])
        self.assertEqual(config["tutor_system_prompt"], "")

    def test_get_tutor_config_returns_none_for_missing_track(self):
        self.assertIsNone(get_tutor_config(self.session, 999))

    def test_enable_tutor_sets_flag_and_prompt(self):
        result = enable_tutor(self.session, self.track["id"], "You are a patient anatomy tutor.")
        self.assertTrue(result["tutor_enabled"])
        self.assertEqual(result["tutor_system_prompt"], "You are a patient anatomy tutor.")

    def test_enable_tutor_rejects_blank_prompt(self):
        with self.assertRaises(ValueError):
            enable_tutor(self.session, self.track["id"], "   ")

    def test_enable_tutor_returns_none_for_missing_track(self):
        self.assertIsNone(enable_tutor(self.session, 999, "prompt"))

    def test_disable_tutor_keeps_prompt_and_history(self):
        enable_tutor(self.session, self.track["id"], "You are a tutor.")
        add_message(self.session, self.track["id"], "user", "hello")
        result = disable_tutor(self.session, self.track["id"])
        self.assertFalse(result["tutor_enabled"])
        self.assertEqual(result["tutor_system_prompt"], "You are a tutor.")
        self.assertEqual(len(list_messages(self.session, self.track["id"])), 1)

    def test_add_and_list_messages_in_order(self):
        add_message(self.session, self.track["id"], "user", "first")
        add_message(self.session, self.track["id"], "assistant", "second")
        messages = list_messages(self.session, self.track["id"])
        self.assertEqual([m["content"] for m in messages], ["first", "second"])
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])

    def test_list_messages_returns_none_for_missing_track(self):
        self.assertIsNone(list_messages(self.session, 999))

    def test_clear_messages_empties_history(self):
        add_message(self.session, self.track["id"], "user", "hello")
        self.assertTrue(clear_messages(self.session, self.track["id"]))
        self.assertEqual(list_messages(self.session, self.track["id"]), [])

    def test_clear_messages_returns_false_for_missing_track(self):
        self.assertFalse(clear_messages(self.session, 999))

    def test_truncate_after_last_user_message_removes_the_reply_and_returns_the_question(self):
        tid = self.track["id"]
        add_message(self.session, tid, "user", "what's 1+1?")
        add_message(self.session, tid, "assistant", "", tool_calls_json="[]")
        add_message(self.session, tid, "tool", "stdout:\n2", tool_name="run_python")
        add_message(self.session, tid, "assistant", "it's 2.")

        result = truncate_after_last_user_message(self.session, tid)

        self.assertEqual(result, "what's 1+1?")
        history = list_messages(self.session, tid)
        self.assertEqual([m["role"] for m in history], ["user"])
        self.assertEqual(history[0]["content"], "what's 1+1?")

    def test_truncate_after_last_user_message_only_removes_messages_after_the_last_one(self):
        tid = self.track["id"]
        add_message(self.session, tid, "user", "first question")
        add_message(self.session, tid, "assistant", "first answer")
        add_message(self.session, tid, "user", "second question")
        add_message(self.session, tid, "assistant", "second answer")

        result = truncate_after_last_user_message(self.session, tid)

        self.assertEqual(result, "second question")
        history = list_messages(self.session, tid)
        self.assertEqual([m["content"] for m in history],
                          ["first question", "first answer", "second question"])

    def test_truncate_after_last_user_message_is_a_noop_when_the_last_message_is_already_a_user_turn(self):
        tid = self.track["id"]
        add_message(self.session, tid, "user", "hello")

        result = truncate_after_last_user_message(self.session, tid)

        self.assertEqual(result, "hello")
        self.assertEqual(len(list_messages(self.session, tid)), 1)

    def test_truncate_after_last_user_message_returns_none_for_an_empty_conversation(self):
        self.assertIsNone(truncate_after_last_user_message(self.session, self.track["id"]))


if __name__ == "__main__":
    unittest.main()
