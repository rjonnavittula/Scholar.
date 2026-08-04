import unittest

from sqlmodel import Session, SQLModel, create_engine

from app.learn_store import create_track_from_spec
from app.tutor_store import (
    add_message, clear_messages, disable_tutor, enable_tutor, get_tutor_config, list_messages,
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


if __name__ == "__main__":
    unittest.main()
