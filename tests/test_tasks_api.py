"""Task CRUD + status/time-log side effects via the API, same TestClient +
in-memory-SQLite pattern as test_api_smoke.py."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
from app.db import get_session


class TestTasksApi(unittest.TestCase):
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
        body = {"title": "Homework 4", "time_needed_min": 60}
        body.update(overrides)
        r = self.client.post("/tasks", json=body, headers=self.headers)
        self.assertEqual(r.status_code, 201)
        return r.json()

    def test_create_and_list(self):
        t = self._create()
        listing = self.client.get("/tasks", headers=self.headers).json()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["id"], t["id"])
        self.assertEqual(listing[0]["remaining_min"], 60)

    def test_list_filters_by_status(self):
        self._create(title="todo one")
        done = self._create(title="already done")
        self.client.patch(f"/tasks/{done['id']}", json={"status": "done"}, headers=self.headers)

        todos = self.client.get("/tasks", params={"status": "todo"}, headers=self.headers).json()
        dones = self.client.get("/tasks", params={"status": "done"}, headers=self.headers).json()
        self.assertEqual([t["title"] for t in todos], ["todo one"])
        self.assertEqual([t["title"] for t in dones], ["already done"])

    def test_patch_updates_fields(self):
        t = self._create()
        r = self.client.patch(f"/tasks/{t['id']}", json={"title": "renamed", "priority_flag": True},
                               headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["title"], "renamed")
        self.assertTrue(r.json()["priority_flag"])

    def test_patch_missing_task_returns_404(self):
        r = self.client.patch("/tasks/999999", json={"title": "x"}, headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_marking_done_sets_completed_at_and_logs_remaining_spent_gap(self):
        t = self._create(time_needed_min=60)
        # simulate 20 min already spent but never logged via /tasks/{id}/log
        self.client.patch(f"/tasks/{t['id']}", json={"time_spent_min": 20}, headers=self.headers)

        r = self.client.patch(f"/tasks/{t['id']}", json={"status": "done"}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "done")
        self.assertIsNotNone(body["completed_at"])

    def test_uncompleting_clears_completed_at(self):
        t = self._create()
        self.client.patch(f"/tasks/{t['id']}", json={"status": "done"}, headers=self.headers)
        r = self.client.patch(f"/tasks/{t['id']}", json={"status": "todo"}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["completed_at"])

    def test_log_time_accumulates_time_spent(self):
        t = self._create()
        r1 = self.client.post(f"/tasks/{t['id']}/log", params={"minutes": 15}, headers=self.headers)
        r2 = self.client.post(f"/tasks/{t['id']}/log", params={"minutes": 10}, headers=self.headers)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.json()["time_spent_min"], 25)

    def test_log_time_rejects_non_positive_minutes(self):
        t = self._create()
        r = self.client.post(f"/tasks/{t['id']}/log", params={"minutes": 0}, headers=self.headers)
        self.assertEqual(r.status_code, 422)

    def test_log_time_missing_task_returns_404(self):
        r = self.client.post("/tasks/999999/log", params={"minutes": 10}, headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_subtasks_roll_up_under_parent_in_list(self):
        parent = self._create(title="Project", time_needed_min=999)
        self._create(title="Part A", parent_id=parent["id"], time_needed_min=30)
        self._create(title="Part B", parent_id=parent["id"], time_needed_min=45)

        listing = self.client.get("/tasks", headers=self.headers).json()
        # children are nested, not top-level rows
        top_level_titles = [t["title"] for t in listing]
        self.assertIn("Project", top_level_titles)
        self.assertNotIn("Part A", top_level_titles)

        proj = next(t for t in listing if t["title"] == "Project")
        self.assertEqual(len(proj["subtasks"]), 2)
        self.assertEqual(proj["time_needed_min"], 75)  # sum of subtasks, not the parent's own 999

    def test_delete_missing_task_is_a_no_op(self):
        r = self.client.delete("/tasks/999999", headers=self.headers)
        self.assertEqual(r.status_code, 204)

    def test_delete_task_cascades_its_planned_blocks(self):
        t = self._create()
        plan = self.client.post("/planned", json={
            "task_id": t["id"], "start_at": "2026-08-10T12:00:00", "end_at": "2026-08-10T13:00:00",
        }, headers=self.headers)
        self.assertEqual(plan.status_code, 201)

        r = self.client.delete(f"/tasks/{t['id']}", headers=self.headers)
        self.assertEqual(r.status_code, 204)

        remaining_plans = self.client.get("/planned", headers=self.headers).json()
        self.assertEqual(remaining_plans, [])


if __name__ == "__main__":
    unittest.main()
