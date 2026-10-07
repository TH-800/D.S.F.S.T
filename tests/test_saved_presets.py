"""Preset API tests use an in-memory Mongo double; never run injections."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import mongomock
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import metrics_api


class PresetTests(unittest.TestCase):
    def setUp(self):
        # The router receives a callable, so patch its original callable's backing client.
        self.client_patch = patch.object(metrics_api, "_mongo_client", mongomock.MongoClient())
        self.client_patch.start()
        self.client = TestClient(metrics_api.app, base_url="http://127.0.0.1")

    def tearDown(self):
        self.client_patch.stop()

    def test_save_list_load_all_types_and_no_experiment_created(self):
        for failure_type, parameters in [
            ("cpu_stress", {"cpu_percent": 25, "duration_seconds": 10}),
            ("memory_stress", {"memory_mb": 128, "duration_seconds": 5}),
            ("network_latency", {"latency_ms": 0}),
            ("packet_loss", {"packet_loss_percent": 0}),
        ]:
            response = self.client.post("/presets", json={"name": "  Test  ", "failure_type": failure_type, "parameters": parameters})
            self.assertEqual(response.status_code, 201, response.text)
            saved = response.json()
            self.assertEqual(saved["name"], "Test")
            self.assertNotIn("_id", saved)
            self.assertEqual(self.client.get(f'/presets/{saved["preset_id"]}').json(), saved)
        self.assertEqual(len(self.client.get("/presets").json()), 4)
        self.assertEqual(len(self.client.get("/presets?limit=2&offset=2").json()), 2)
        self.assertEqual(metrics_api.get_db()["experiments"].count_documents({}), 0)

    def test_invalid_parameters_rejected_without_saving(self):
        for parameters in [
            {"cpu_percent": 66, "duration_seconds": 10},
            {"cpu_percent": True, "duration_seconds": 10},
            {"cpu_percent": 25.5, "duration_seconds": 10},
            {"cpu_percent": 25, "duration_seconds": 0},
            {"cpu_percent": 25},
            {"cpu_percent": 25, "duration_seconds": 10, "other": 1},
        ]:
            response = self.client.post("/presets", json={"name": "Test", "failure_type": "cpu_stress", "parameters": parameters})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/presets").json(), [])

    def test_blank_name_and_foreign_origin_rejected(self):
        payload = {"name": "   ", "failure_type": "network_latency", "parameters": {"latency_ms": 10}}
        self.assertEqual(self.client.post("/presets", json=payload).status_code, 422)
        payload["name"] = "Valid"
        self.assertEqual(self.client.post("/presets", json=payload, headers={"Origin": "https://example.org"}).status_code, 403)

    def test_missing_and_unavailable_are_explicit_errors(self):
        self.assertEqual(self.client.get("/presets/missing").status_code, 404)
        with patch.object(type(metrics_api.get_db()["saved_presets"]), "find", side_effect=ServerSelectionTimeoutError("offline")):
            self.assertEqual(self.client.get("/presets").status_code, 503)
        with patch.object(type(metrics_api.get_db()["saved_presets"]), "insert_one", side_effect=ServerSelectionTimeoutError("offline")):
            response = self.client.post("/presets", json={"name": "Test", "failure_type": "network_latency", "parameters": {"latency_ms": 10}})
            self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
