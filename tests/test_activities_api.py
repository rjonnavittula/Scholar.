"""Activity CRUD via the API, using the same TestClient + in-memory-SQLite
pattern established in test_api_smoke.py. Covers the PATCH endpoint added to
replace the delete-then-recreate pattern that could leave duplicate rows
behind if a move/resize ever fired twice for the same drag."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
from app.db import get_session


class TestActivitiesApi(unittest.TestCase):
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
        body = {"title": "Lunch", "color": "#B59B5B", "weekday": 1, "start_min": 720, "end_min": 780}
        body.update(overrides)
        r = self.client.post("/activities", json=body, headers=self.headers)
        self.assertEqual(r.status_code, 201)
        return r.json()

    def test_patch_updates_time_in_place_same_id(self):
        act = self._create()
        r = self.client.patch(f"/activities/{act['id']}", json={"start_min": 800, "end_min": 850}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        updated = r.json()
        self.assertEqual(updated["id"], act["id"])
        self.assertEqual(updated["start_min"], 800)
        self.assertEqual(updated["end_min"], 850)
        # untouched fields survive
        self.assertEqual(updated["title"], "Lunch")

        listing = self.client.get("/activities", headers=self.headers).json()
        self.assertEqual(len(listing), 1)

    def test_patch_can_move_to_a_different_weekday(self):
        act = self._create(weekday=1)
        r = self.client.patch(f"/activities/{act['id']}", json={"weekday": 3}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["weekday"], 3)

    def test_patch_rejects_bad_time_range(self):
        act = self._create()
        r = self.client.patch(f"/activities/{act['id']}", json={"start_min": 900, "end_min": 800}, headers=self.headers)
        self.assertEqual(r.status_code, 400)

    def test_patch_missing_activity_returns_404(self):
        r = self.client.patch("/activities/999999", json={"start_min": 100}, headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_double_patch_never_duplicates(self):
        """The bug this endpoint replaces: a drag/resize firing twice used to
        leave two rows behind (delete-then-create, with an idempotent delete
        silently no-op'ing the second time). PATCH is update-in-place, so
        firing the same move twice just re-applies the same values."""
        act = self._create()
        r1 = self.client.patch(f"/activities/{act['id']}", json={"start_min": 800, "end_min": 850}, headers=self.headers)
        r2 = self.client.patch(f"/activities/{act['id']}", json={"start_min": 800, "end_min": 850}, headers=self.headers)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        listing = self.client.get("/activities", headers=self.headers).json()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["start_min"], 800)

    def test_delete_missing_activity_is_a_no_op_not_an_error(self):
        # Documents the existing idempotent-delete behavior this fix works
        # around — deleting an already-gone id must not raise.
        r = self.client.delete("/activities/999999", headers=self.headers)
        self.assertEqual(r.status_code, 204)


if __name__ == "__main__":
    unittest.main()
