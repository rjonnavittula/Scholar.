"""First use of FastAPI's TestClient in this repo.

Scoped deliberately to the auth lifecycle (mint / list / revoke keys) rather
than exhaustive route-by-route coverage of app/api.py — that's a much larger,
separate effort. This mainly proves out the dependency-override pattern for
future API-level tests: swap get_session for an in-memory SQLite session and
skip the real lifespan's init_db()/Alembic bootstrap.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
from app.db import get_session


class TestApiSmoke(unittest.TestCase):
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

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self._init_db_patcher.stop()
        main_module.app.dependency_overrides.clear()
        self.engine.dispose()

    def test_key_lifecycle_mint_list_revoke(self):
        mint = self.client.post("/auth/keys", params={"label": "test-key"})
        self.assertEqual(mint.status_code, 200)
        api_key = mint.json()["api_key"]
        key_id = mint.json()["id"]

        listed = self.client.get("/auth/keys", headers={"X-API-Key": api_key})
        self.assertEqual(listed.status_code, 200)
        labels = [k["label"] for k in listed.json()]
        self.assertIn("test-key", labels)
        self.assertNotIn("hashed_key", listed.json()[0])

        revoke = self.client.post(f"/auth/keys/{key_id}/revoke", headers={"X-API-Key": api_key})
        self.assertEqual(revoke.status_code, 200)
        self.assertTrue(revoke.json()["revoked"])

        after = self.client.get("/auth/keys", headers={"X-API-Key": api_key})
        self.assertEqual(after.status_code, 401)

    def test_invalid_key_rejected(self):
        r = self.client.get("/auth/keys", headers={"X-API-Key": "hive_not_a_real_key"})
        self.assertEqual(r.status_code, 401)

    def test_missing_key_header_rejected(self):
        r = self.client.get("/auth/keys")
        self.assertIn(r.status_code, (401, 422))

    def test_revoke_missing_key_returns_404(self):
        mint = self.client.post("/auth/keys", params={"label": "revoker"})
        api_key = mint.json()["api_key"]
        r = self.client.post("/auth/keys/999999/revoke", headers={"X-API-Key": api_key})
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
