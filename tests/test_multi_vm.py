"""Exercise the real API routes and persistent state without launching host faults."""
import copy
import sys
import threading
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".test-deps"))
import mongomock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError
import experiment_orchestrator as orchestrator
import metrics_api
import multi_vm
import vm_metrics
from vm_registry import VMRegistry, RegisterVMRequest, normalise_vm_url, vm_request


class FakeAgents:
    def __init__(self, db):
        self.db = db
        self.records = {}
        self.busy = set()
        self.offline = set()
        self.fail_start = set()
        self.fail_stop = set()
        self.barrier = None
        self.started = []

    def request(self, vm, port, path, method="GET", payload=None):
        vm_id = vm["vm_id"]
        if vm_id in self.offline:
            raise HTTPException(503, "VM offline")
        records = self.records.setdefault(vm_id, {})
        if path == "/state":
            active = next((key for key, record in records.items() if record["status"] == "running"), None)
            return {"state": "running" if active or vm_id in self.busy else "idle",
                    "active_experiment_id": active}
        if path == "/metrics/latest":
            return {"cpu": {"cpu_usage_percent": 77, "timestamp": datetime.now(timezone.utc).isoformat()},
                    "memory": {"memory_percent": 32, "memory_used_mb": 900, "timestamp": "now"},
                    "network": {"latency_ms": 13, "packet_loss_percent": 0,
                                "throughput_kbps": 20, "timestamp": "now"}}
        if path.startswith("/metrics/history"):
            return {"measurement": "cpu", "minutes": 15,
                    "series": {"cpu_usage_percent": [{"timestamp": "now", "value": 77}]}}
        if method == "POST" and path == "/experiments":
            key = str(uuid.uuid4())
            records[key] = {"experiment_id": key, "status": "created", "parameters": payload["parameters"]}
            return {"experiment_id": key, "status": "created"}
        key = path.split("/")[2]
        if method == "GET":
            if key not in records:
                raise HTTPException(404, "Child not found")
            return dict(records[key])
        if path.endswith("/start"):
            # Prove the coordinator recorded the child before allowing injection.
            saved = self.db["experiment_batches"].find_one({"members.experiment_id": key})
            if not saved:
                raise AssertionError("Child was not journalled before startup")
            records[key]["status"] = "running"
            self.started.append(vm_id)
            if self.barrier:
                self.barrier.wait(timeout=3)
            if vm_id in self.fail_start:
                raise HTTPException(503, "Start response was lost after injection")
            return {"status": "running"}
        if path.endswith("/stop"):
            if vm_id in self.fail_stop:
                raise HTTPException(503, "Reset unavailable")
            records[key]["status"] = "completed"
            return {"status": "completed"}
        raise AssertionError(path)


class MultiVMTests(unittest.TestCase):
    def setUp(self):
        self.db = mongomock.MongoClient()["dsfst"]
        self.agents = FakeAgents(self.db)
        self.patches = [
            patch.object(orchestrator, "_get_mongo", return_value=self.db),
            patch.object(metrics_api, "get_db", return_value=self.db),
            patch.object(multi_vm, "vm_request", side_effect=self.agents.request),
            patch.object(vm_metrics, "vm_request", side_effect=self.agents.request),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.client = TestClient(orchestrator.app, base_url="http://127.0.0.1")
        self.metrics = TestClient(metrics_api.app, base_url="http://127.0.0.1")
        response = self.client.post("/vms", json={"name": "Clone", "base_url": "http://192.168.56.11:3000/"})
        self.assertEqual(response.status_code, 201, response.text)
        self.remote = response.json()["vm_id"]
        self.body = {"name": "two VMs", "failure_type": "cpu",
                     "parameters": {"cpu_percent": 10, "duration_seconds": 15},
                     "vm_ids": ["local", self.remote]}

    def launch(self):
        return self.client.post("/experiments/launch", json=self.body)

    def test_registry_persists_normalises_and_removes(self):
        fresh = VMRegistry(lambda: self.db)
        self.assertEqual(len(fresh.list()), 2)
        self.assertEqual(fresh.get(self.remote)["base_url"], "http://192.168.56.11:3000")
        duplicate = self.client.post("/vms", json={"name": "Other", "base_url": "http://192.168.56.11:3000"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.client.delete("/vms/local").status_code, 409)
        self.assertEqual(self.client.delete("/vms/" + self.remote).status_code, 200)
        self.assertEqual(self.client.delete("/vms/" + self.remote).status_code, 404)
        self.assertEqual(self.client.get("/vms").json()[0]["vm_id"], "local")

    def test_registration_rejects_non_vm_destinations_and_foreign_origin(self):
        for url in ("http://127.0.0.1:3000", "http://169.254.169.254:3000",
                    "http://example.org:3000", "http://192.168.56.11:8086",
                    "http://user:secret@192.168.56.11:3000",
                    "http://192.168.56.11:3000/api", "http://192.168.56.11:3000?x=1"):
            response = self.client.post("/vms", json={"name": "invalid", "base_url": url})
            self.assertEqual(response.status_code, 422, url)
        self.assertEqual(self.client.post("/vms", json={"name": "x", "base_url": "http://192.168.56.12:3000"},
            headers={"Origin": "https://example.org"}).status_code, 403)

    def test_per_vm_metrics_do_not_fall_back_to_another_vm(self):
        with patch.object(metrics_api, "get_influx", return_value=None):
            local = self.metrics.get("/metrics/latest?vm_id=local")
        remote = self.metrics.get("/vms/" + self.remote + "/metrics/latest")
        self.assertEqual(local.status_code, 200)
        self.assertEqual(local.json()["vm_id"], "local")
        self.assertIsNone(local.json()["cpu"])
        self.assertEqual(remote.json()["vm_id"], self.remote)
        self.assertEqual(remote.json()["cpu"]["cpu_usage_percent"], 77)
        self.assertEqual(self.metrics.get("/metrics/latest?vm_id=missing").status_code, 404)
        self.agents.offline.add(self.remote)
        self.assertEqual(self.metrics.get("/metrics/latest?vm_id=" + self.remote).status_code, 503)

    def test_scoped_history_and_validation(self):
        response = self.metrics.get("/vms/" + self.remote + "/metrics/history?measurement=cpu&minutes=15")
        self.assertEqual(response.json()["vm_id"], self.remote)
        self.assertEqual(response.json()["series"]["cpu_usage_percent"][0]["value"], 77)
        self.assertEqual(self.metrics.get("/metrics/history?measurement=not-a-metric").status_code, 422)
        self.assertEqual(self.metrics.get("/metrics/history?minutes=0").status_code, 422)

    def test_one_request_launches_both_in_parallel_and_tracks_each_child(self):
        self.agents.barrier = threading.Barrier(2)
        response = self.launch()
        self.assertEqual(response.status_code, 201, response.text)
        batch = response.json()
        self.assertEqual(batch["status"], "running")
        self.assertEqual(set(self.agents.started), {"local", self.remote})
        ids = [m["experiment_id"] for m in batch["members"]]
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(self.client.delete("/vms/" + self.remote).status_code, 409)
        for records in self.agents.records.values():
            for record in records.values():
                record["status"] = "completed"
        done = self.client.get("/experiment-batches/" + batch["batch_id"]).json()
        self.assertEqual(done["status"], "completed")
        self.assertTrue(done["ended_at"])
        self.assertEqual(self.client.delete("/vms/" + self.remote).status_code, 200)

    def test_children_finishing_at_different_times_keep_batch_running(self):
        batch = self.launch().json()
        path = "/experiment-batches/" + batch["batch_id"]
        local = next(m for m in batch["members"] if m["vm_id"] == "local")
        remote = next(m for m in batch["members"] if m["vm_id"] == self.remote)
        self.agents.records["local"][local["experiment_id"]]["status"] = "completed"
        current = self.client.get(path).json()
        self.assertEqual(current["status"], "running")
        self.assertIsNone(current["ended_at"])
        self.assertEqual({m["status"] for m in current["members"]}, {"running", "completed"})
        self.assertEqual(self.client.delete("/vms/" + self.remote).status_code, 409)
        self.agents.records[self.remote][remote["experiment_id"]]["status"] = "completed"
        done = self.client.get(path).json()
        self.assertEqual(done["status"], "completed")
        self.assertTrue(done["ended_at"])

    def test_offline_or_busy_preflight_starts_nothing(self):
        self.agents.busy.add("local")
        self.assertEqual(self.launch().status_code, 409)
        self.assertFalse(self.agents.started)
        self.agents.busy.clear()
        self.agents.offline.add(self.remote)
        self.assertEqual(self.launch().status_code, 503)
        self.assertFalse(self.agents.started)
        self.assertEqual(self.db["experiment_batches"].count_documents({}), 0)

    def test_invalid_requests_have_no_side_effects(self):
        for change in ({"vm_ids": ["local", "local"]}, {"vm_ids": ["missing"]},
                       {"parameters": {"cpu_percent": 100}}, {"vm_ids": []},
                       {"target_container": "other-host"}):
            body = {**self.body, **change}
            self.assertIn(self.client.post("/experiments/launch", json=body).status_code, (404, 422))
        self.assertFalse(self.agents.started)
        self.assertEqual(self.db["experiment_batches"].count_documents({}), 0)

    def test_failed_launch_resets_successful_and_ambiguous_children(self):
        self.agents.fail_start.add(self.remote)
        response = self.launch()
        self.assertEqual(response.status_code, 207)
        self.assertEqual(response.json()["status"], "failed")
        self.assertTrue(response.json()["launch_errors"])
        self.assertTrue(all(record["status"] == "completed"
            for records in self.agents.records.values() for record in records.values()))

    def test_unconfirmed_reset_remains_visible_and_can_be_retried(self):
        self.agents.fail_start.add(self.remote)
        self.agents.fail_stop.add(self.remote)
        batch = self.launch().json()
        self.assertEqual(batch["status"], "partial_failure")
        self.assertEqual(self.client.delete("/vms/" + self.remote).status_code, 409)
        self.agents.fail_stop.clear()
        stopped = self.client.post("/experiment-batches/" + batch["batch_id"] + "/stop")
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["status"], "stopped")

    def test_busy_race_rejects_child_and_preserves_the_other_experiment(self):
        original = self.agents.request
        def request(vm, port, path, method="GET", payload=None):
            if vm["vm_id"] == self.remote:
                if path.endswith("/start"):
                    self.agents.busy.add(self.remote)
                    raise HTTPException(409, "Another experiment started after preflight")
                if path == "/state" and self.remote in self.agents.busy:
                    return {"state":"running", "active_experiment_id":"another-experiment"}
                if path.endswith("/stop"):
                    self.fail("A rejected child must not reset another active experiment")
            return original(vm, port, path, method, payload)
        with patch.object(multi_vm, "vm_request", side_effect=request):
            response = self.launch()
        self.assertEqual(response.status_code, 207)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(self.agents.started, ["local"])
        self.assertIn(self.remote, self.agents.busy)
        self.assertTrue(all(r["status"] == "completed" for r in self.agents.records["local"].values()))
        self.assertTrue(all(r["status"] == "created" for r in self.agents.records[self.remote].values()))

    def test_missing_started_record_stays_active_until_reset_confirmed(self):
        batch = self.launch().json()
        child = next(m for m in batch["members"] if m["vm_id"] == self.remote)
        self.agents.records[self.remote][child["experiment_id"]]["status"] = "created"
        self.agents.fail_stop.add(self.remote)
        path = "/experiment-batches/" + batch["batch_id"]
        current = self.client.get(path).json()
        self.assertEqual(current["status"], "partial_failure")
        stopped = self.client.post(path + "/stop")
        self.assertEqual(stopped.status_code, 207)
        self.assertEqual(stopped.json()["status"], "partial_failure")
        self.assertEqual(self.client.delete("/vms/" + self.remote).status_code, 409)
        self.agents.fail_stop.clear()
        self.assertEqual(self.client.post(path + "/stop").json()["status"], "stopped")

    def test_persisted_batch_can_be_stopped_after_manager_restart(self):
        batch = self.launch().json()
        manager = multi_vm.BatchManager(lambda: self.db, VMRegistry(lambda: self.db),
                                         orchestrator._normalise_parameters)
        stopped = manager.stop(batch["batch_id"])
        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(manager.stop(batch["batch_id"])["status"], "stopped")

    def test_stale_start_is_reconciled_after_coordinator_restart(self):
        batch = self.launch().json()
        self.db["experiment_batches"].update_one({"batch_id": batch["batch_id"]},
            {"$set": {"status": "starting", "lease_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
        current = self.client.get("/experiment-batches/" + batch["batch_id"]).json()
        self.assertEqual(current["status"], "running")
        self.assertEqual(self.client.post("/experiment-batches/emergency-stop").json()["status"], "stopped")

    def test_stale_stop_recovers_but_fresh_stop_keeps_its_claim(self):
        batch = self.launch().json()
        batch_id = batch["batch_id"]
        collection = self.db["experiment_batches"]
        collection.update_one({"batch_id": batch_id}, {"$set": {
            "status": "stopping", "operation_id": "interrupted-stop",
            "lease_until": datetime.now(timezone.utc) + timedelta(seconds=180)}})
        self.assertEqual(self.client.get("/experiment-batches/" + batch_id).json()["status"], "stopping")
        self.assertEqual(self.client.post("/experiment-batches/" + batch_id + "/stop").status_code, 409)
        collection.update_one({"batch_id": batch_id}, {"$set": {
            "lease_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
        manager = multi_vm.BatchManager(lambda: self.db, VMRegistry(lambda: self.db),
                                       orchestrator._normalise_parameters)
        stopped = manager.stop(batch_id)
        self.assertEqual(stopped["status"], "stopped")
        self.assertNotEqual(stopped["operation_id"], "interrupted-stop")
        self.assertTrue(all(m["status"] == "completed" for m in stopped["members"]))
        # An old request cannot overwrite a newer operation's completed result.
        old_write = collection.update_one({"batch_id": batch_id, "status": "stopping",
            "operation_id": "interrupted-stop"}, {"$set": {"status": "partial_failure"}})
        self.assertEqual(old_write.matched_count, 0)

    def test_active_filter_finds_old_batches_before_new_finished_records(self):
        batch = self.launch().json()
        for i in range(12):
            self.db["experiment_batches"].insert_one({"batch_id": str(uuid.uuid4()),
                "status": "completed", "created_at": datetime.now(timezone.utc), "members": []})
        listed = self.client.get("/experiment-batches?active_only=true").json()
        self.assertEqual([item["batch_id"] for item in listed], [batch["batch_id"]])

    def test_database_failure_prevents_injection(self):
        with patch.object(self.db["experiment_batches"], "insert_one", side_effect=PyMongoError("offline")):
            self.assertEqual(self.launch().status_code, 503)
        self.assertFalse(self.agents.started)

    def test_transport_does_not_follow_redirects_or_environment_proxies(self):
        vm = {"name": "Clone", "base_url": "http://192.168.56.11:3000", "is_local": False}
        session = MagicMock()
        session.request.return_value.status_code = 302
        session.request.return_value.json.return_value = {}
        with patch("vm_registry.requests.Session") as factory:
            factory.return_value.__enter__.return_value = session
            with self.assertRaises(HTTPException):
                vm_request(vm, 8008, "/metrics/latest")
        self.assertFalse(session.trust_env)
        self.assertFalse(session.request.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
