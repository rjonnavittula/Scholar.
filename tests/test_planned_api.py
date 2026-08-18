"""PlannedBlock (a task's "DO date") CRUD via the API, same TestClient +
in-memory-SQLite pattern as test_api_smoke.py."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
from app.db import get_session


class TestPlannedApi(unittest.TestCase):
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
        self.task = self.client.post("/tasks", json={"title": "Homework 4", "time_needed_min": 60},
                                      headers=self.headers).json()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self._init_db_patcher.stop()
        main_module.app.dependency_overrides.clear()
        self.engine.dispose()

    def _create(self, **overrides):
        body = {"task_id": self.task["id"], "start_at": "2026-08-10T12:00:00", "end_at": "2026-08-10T13:00:00"}
        body.update(overrides)
        return self.client.post("/planned", json=body, headers=self.headers)

    def test_create_and_list(self):
        r = self._create()
        self.assertEqual(r.status_code, 201)
        listing = self.client.get("/planned", headers=self.headers).json()
        self.assertEqual(len(listing), 1)

    def test_create_rejects_end_before_start(self):
        r = self._create(start_at="2026-08-10T13:00:00", end_at="2026-08-10T12:00:00")
        self.assertEqual(r.status_code, 400)

    def test_create_rejects_missing_task(self):
        r = self._create(task_id=999999)
        self.assertEqual(r.status_code, 404)

    def test_patch_updates_time(self):
        p = self._create().json()
        r = self.client.patch(f"/planned/{p['id']}", json={
            "start_at": "2026-08-10T14:00:00", "end_at": "2026-08-10T15:00:00",
        }, headers=self.headers)
        self.assertEqual(r.status_code, 200)

    def test_patch_missing_block_returns_404(self):
        r = self.client.patch("/planned/999999", json={"completed": True}, headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_completing_a_block_logs_its_duration_onto_the_task(self):
        p = self._create(start_at="2026-08-10T12:00:00", end_at="2026-08-10T13:30:00").json()  # 90 min
        r = self.client.patch(f"/planned/{p['id']}", json={"completed": True}, headers=self.headers)
        self.assertEqual(r.status_code, 200)

        task = self.client.get("/tasks", headers=self.headers).json()[0]
        self.assertEqual(task["time_spent_min"], 90)

    def test_recompleting_an_already_completed_block_does_not_double_log(self):
        p = self._create(start_at="2026-08-10T12:00:00", end_at="2026-08-10T13:30:00").json()
        self.client.patch(f"/planned/{p['id']}", json={"completed": True}, headers=self.headers)
        # patch it again with completed:true (already was) - should not re-add 90 min
        self.client.patch(f"/planned/{p['id']}", json={"completed": True}, headers=self.headers)

        task = self.client.get("/tasks", headers=self.headers).json()[0]
        self.assertEqual(task["time_spent_min"], 90)

    def test_delete_missing_block_is_a_no_op(self):
        r = self.client.delete("/planned/999999", headers=self.headers)
        self.assertEqual(r.status_code, 204)

    def test_delete_removes_the_block(self):
        p = self._create().json()
        r = self.client.delete(f"/planned/{p['id']}", headers=self.headers)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.client.get("/planned", headers=self.headers).json(), [])


if __name__ == "__main__":
    unittest.main()
