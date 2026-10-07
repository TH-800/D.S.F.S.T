# AI-assisted API tests with an in-memory fake collection, not a live MongoDB test.
import copy
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from preset_api import build_presets_router

class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda item: item[key], reverse=direction == -1))
    def limit(self, count): return Cursor(self[:count])

class Collection:
    def __init__(self): self.docs = []; self.fail = False
    def check(self):
        if self.fail: raise PyMongoError("private database detail")
    def create_index(self, *args, **kwargs): self.check()
    def insert_one(self, doc):
        self.check()
        if any(item["name"] == doc["name"] for item in self.docs): raise DuplicateKeyError("duplicate")
        self.docs.append(copy.deepcopy(doc))
    def find(self, *args): self.check(); return Cursor(copy.deepcopy(self.docs))
    def find_one(self, query, projection):
        self.check()
        return next((copy.deepcopy(d) for d in self.docs if d["preset_id"] == query["preset_id"]), None)

class PresetRoutesTests(unittest.TestCase):
    def setUp(self):
        self.collection = Collection()
        app = FastAPI()
        app.include_router(build_presets_router(lambda: {"saved_presets": self.collection}, lambda doc: doc))
        self.client = TestClient(app)
        self.body = {"name": "Demo", "failure_type": "cpu", "parameters": {"cpu_percent": 20, "duration_seconds": 10}}
    def test_save_list_load(self):
        response = self.client.post("/presets", json=self.body)
        self.assertEqual(response.status_code, 201)
        saved = response.json()
        self.assertEqual(saved["parameters"], self.body["parameters"])
        self.assertEqual(self.client.get("/presets").json(), [saved])
        self.assertEqual(self.client.get("/presets/" + saved["preset_id"]).json(), saved)
    def test_duplicate_name(self):
        self.client.post("/presets", json=self.body)
        self.assertEqual(self.client.post("/presets", json=self.body).status_code, 409)
        self.assertEqual(len(self.collection.docs), 1)
    def test_validation(self):
        self.body["parameters"]["cpu_percent"] = 66
        self.assertEqual(self.client.post("/presets", json=self.body).status_code, 422)
        self.assertEqual(self.collection.docs, [])
    def test_missing(self):
        self.assertEqual(self.client.get("/presets/missing").status_code, 404)
    def test_database_failure(self):
        self.collection.fail = True
        for method, path in [("GET", "/presets"), ("GET", "/presets/missing"), ("POST", "/presets")]:
            response = self.client.request(method, path, json=self.body if method == "POST" else None)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private database detail", response.text)

if __name__ == "__main__": unittest.main()
