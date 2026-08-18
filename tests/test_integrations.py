import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from sqlmodel import Session, SQLModel, create_engine, select

from app.crypto import encrypt_secret
from app.integrations import sync_canvas
from app.models import Course, Settings, Task


def _assignment(id_, name, due_at=None, html_url=""):
    return SimpleNamespace(id=id_, name=name, due_at=due_at, html_url=html_url)


def _course(id_, name, assignments):
    c = MagicMock()
    c.id = id_
    c.name = name
    c.get_assignments.return_value = assignments
    return c


class TestSyncCanvas(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.settings = Settings(id=1, canvas_base_url="https://psu.instructure.com",
                                  canvas_token="plain-token", start_ahead_days=3)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_creates_course_and_task_for_new_assignment(self):
        course = _course(101, "CMPSC 465", [_assignment(9001, "HW1")])
        mock_canvas = MagicMock()
        mock_canvas.get_courses.return_value = [course]

        with patch("canvasapi.Canvas", return_value=mock_canvas) as MockCanvas:
            result = sync_canvas(self.session, self.settings)

        MockCanvas.assert_called_once_with("https://psu.instructure.com", "plain-token")
        self.assertEqual(result, {"courses": 1, "created": 1, "updated": 0})
        saved_course = self.session.exec(select(Course).where(Course.external_id == "canvas:101")).first()
        self.assertIsNotNone(saved_course)
        saved_task = self.session.exec(select(Task).where(Task.external_id == "canvas:9001")).first()
        self.assertEqual(saved_task.title, "HW1")
        self.assertEqual(saved_task.course_id, saved_course.id)

    def test_updates_existing_task_matched_by_external_id(self):
        self.session.add(Course(name="CMPSC 465", external_id="canvas:101"))
        self.session.add(Task(title="old title", external_id="canvas:9001"))
        self.session.commit()

        course = _course(101, "CMPSC 465", [_assignment(9001, "new title")])
        mock_canvas = MagicMock()
        mock_canvas.get_courses.return_value = [course]

        with patch("canvasapi.Canvas", return_value=mock_canvas):
            result = sync_canvas(self.session, self.settings)

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["created"], 0)
        task = self.session.exec(select(Task).where(Task.external_id == "canvas:9001")).first()
        self.assertEqual(task.title, "new title")

    def test_skips_courses_with_no_name(self):
        course = _course(101, None, [])
        mock_canvas = MagicMock()
        mock_canvas.get_courses.return_value = [course]

        with patch("canvasapi.Canvas", return_value=mock_canvas):
            result = sync_canvas(self.session, self.settings)

        self.assertEqual(result, {"courses": 0, "created": 0, "updated": 0})

    def test_propagates_client_errors(self):
        mock_canvas = MagicMock()
        mock_canvas.get_courses.side_effect = RuntimeError("bad token")

        with patch("canvasapi.Canvas", return_value=mock_canvas):
            with self.assertRaises(RuntimeError):
                sync_canvas(self.session, self.settings)

    def test_decrypts_token_before_calling_canvas_client(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": key}):
            self.settings.canvas_token = encrypt_secret("real-token")
            mock_canvas = MagicMock()
            mock_canvas.get_courses.return_value = []
            with patch("canvasapi.Canvas", return_value=mock_canvas) as MockCanvas:
                sync_canvas(self.session, self.settings)
            MockCanvas.assert_called_once_with("https://psu.instructure.com", "real-token")


if __name__ == "__main__":
    unittest.main()
