"""Settings + term config via the API, same TestClient + in-memory-SQLite
pattern as test_api_smoke.py."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
from app.db import get_session


class TestConfigApi(unittest.TestCase):
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

    def test_get_settings_returns_defaults_when_none_saved_yet(self):
        r = self.client.get("/config/settings", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("min_block_min", body)
        self.assertIn("home_tz", body)

    def test_get_settings_never_echoes_the_raw_canvas_secret(self):
        self.client.put("/config/settings", json={"canvas_token": "super-secret-token"}, headers=self.headers)
        r = self.client.get("/config/settings", headers=self.headers)
        self.assertIs(r.json()["canvas_token"], True)  # masked to a bool, not the raw value

    def test_put_settings_persists_and_get_reflects_it(self):
        r = self.client.put("/config/settings", json={"theme": "dark", "home_tz": "America/Chicago"},
                             headers=self.headers)
        self.assertEqual(r.status_code, 200)

        after = self.client.get("/config/settings", headers=self.headers).json()
        self.assertEqual(after["theme"], "dark")
        self.assertEqual(after["home_tz"], "America/Chicago")

    def test_put_settings_ignores_unknown_fields(self):
        r = self.client.put("/config/settings", json={"not_a_real_field": "x"}, headers=self.headers)
        self.assertEqual(r.status_code, 200)  # silently ignored, not a validation error

    def test_get_term_returns_null_term_and_empty_holidays_before_any_save(self):
        r = self.client.get("/config/term", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["term"])
        self.assertEqual(r.json()["holidays"], [])

    def test_put_term_persists_dates(self):
        r = self.client.put("/config/term", json={
            "name": "Fall 2026", "classes_start": "2026-08-24", "classes_end": "2026-12-12",
        }, headers=self.headers)
        self.assertEqual(r.status_code, 200)

        after = self.client.get("/config/term", headers=self.headers).json()
        self.assertEqual(after["term"]["name"], "Fall 2026")
        self.assertEqual(after["term"]["classes_start"], "2026-08-24")

    def test_add_and_delete_holiday(self):
        r = self.client.post("/config/holidays", json={"day": "2026-11-26", "name": "Thanksgiving"},
                              headers=self.headers)
        self.assertEqual(r.status_code, 201)
        hid = r.json()["id"]

        after = self.client.get("/config/term", headers=self.headers).json()
        self.assertEqual(len(after["holidays"]), 1)

        d = self.client.delete(f"/config/holidays/{hid}", headers=self.headers)
        self.assertEqual(d.status_code, 204)
        after2 = self.client.get("/config/term", headers=self.headers).json()
        self.assertEqual(after2["holidays"], [])

    def test_list_timezones_defaults_to_us(self):
        r = self.client.get("/config/timezones", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("US", body["countries"])
        self.assertTrue(any(z["id"] == "America/New_York" for z in body["zones"]))

    def test_list_timezones_for_another_country(self):
        r = self.client.get("/config/timezones", params={"country": "GB"}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        zone_ids = [z["id"] for z in r.json()["zones"]]
        self.assertIn("Europe/London", zone_ids)


if __name__ == "__main__":
    unittest.main()
