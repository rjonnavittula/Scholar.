"""Course CRUD via the API, same TestClient + in-memory-SQLite pattern as
test_api_smoke.py / test_activities_api.py. Includes a regression test for
the delete_course FK-violation bug: deleting a course with linked tasks or
activities used to 500 instead of nulling course_id like the UI's own
confirm text ("...and keep its tasks") always promised."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
from app.db import get_session


class TestCoursesApi(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                                     poolclass=StaticPool)
        SQLModel.metadata.create_all(self.engine)

        def _override_get_session():
            with Session(self.engine) as session:
                yield session

        main_module.app.dependency_overrides[get_session] = _override_get_session
        self._init_db_patcher = patch("app.main.init_db")
        self._init_db_patcher.start()
        self.client = TestClient(main_module.app)
        self.client.__enter__()

        mint = self.client.post("/auth/keys", params={"label": "test"})
        self.headers = {"X-API-Key": mint.json()["api_key"]}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self._init_db_patcher.stop()
        main_module.app.dependency_overrides.clear()
        self.engine.dispose()

    def _create(self, **overrides):
        body = {"name": "CMPEN 331", "color": "#5B5FEF"}
        body.update(overrides)
        r = self.client.post("/courses", json=body, headers=self.headers)
        self.assertEqual(r.status_code, 201)
        return r.json()

    def test_create_and_list(self):
        c = self._create()
        listing = self.client.get("/courses", headers=self.headers).json()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["id"], c["id"])

    def test_patch_updates_fields(self):
        c = self._create()
        r = self.client.patch(f"/courses/{c['id']}", json={"name": "CMPEN 331 (renamed)", "credits": 3},
                               headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "CMPEN 331 (renamed)")
        self.assertEqual(r.json()["credits"], 3)

    def test_patch_missing_course_returns_404(self):
        r = self.client.patch("/courses/999999", json={"name": "x"}, headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_delete_missing_course_is_a_no_op(self):
        r = self.client.delete("/courses/999999", headers=self.headers)
        self.assertEqual(r.status_code, 204)

    def test_delete_course_with_no_links(self):
        c = self._create()
        r = self.client.delete(f"/courses/{c['id']}", headers=self.headers)
        self.assertEqual(r.status_code, 204)
        listing = self.client.get("/courses", headers=self.headers).json()
        self.assertEqual(listing, [])

    def test_delete_course_keeps_linked_task_and_nulls_course_id(self):
        c = self._create()
        task = self.client.post("/tasks", json={"title": "PS1", "course_id": c["id"], "time_needed_min": 60},
                                 headers=self.headers).json()

        r = self.client.delete(f"/courses/{c['id']}", headers=self.headers)
        self.assertEqual(r.status_code, 204, "delete must not 500 on a linked task's FK")

        tasks = self.client.get("/tasks", headers=self.headers).json()
        survivor = next(t for t in tasks if t["id"] == task["id"])
        self.assertIsNone(survivor["course_id"])

    def test_delete_course_keeps_linked_activity_and_nulls_course_id(self):
        c = self._create()
        act = self.client.post("/activities", json={
            "title": "Lecture", "color": "#5B5FEF", "weekday": 1,
            "start_min": 600, "end_min": 650, "course_id": c["id"],
        }, headers=self.headers).json()

        r = self.client.delete(f"/courses/{c['id']}", headers=self.headers)
        self.assertEqual(r.status_code, 204, "delete must not 500 on a linked activity's FK")

        acts = self.client.get("/activities", headers=self.headers).json()
        survivor = next(a for a in acts if a["id"] == act["id"])
        self.assertIsNone(survivor["course_id"])


if __name__ == "__main__":
    unittest.main()
