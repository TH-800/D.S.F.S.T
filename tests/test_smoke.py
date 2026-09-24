"""Smoke tests that never launch stress-ng, tc, or database containers."""

import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import requests

from fastapi import HTTPException
from fastapi.testclient import TestClient
from dotenv import dotenv_values
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "InjectionScripts"))

import BaseNetworkInfo as network_info
import experiment_orchestrator as orchestrator
import metrics_writer
import network_rules


class ParameterTests(unittest.TestCase):
    def test_legacy_and_current_parameters_have_one_validated_shape(self):
        self.assertEqual(
            orchestrator._normalise_parameters("cpu", {"cpuPercent": 27, "duration": 12}),
            {"cpu_percent": 27, "duration_seconds": 12},
        )
        self.assertEqual(
            orchestrator._normalise_parameters("latency", {"latency_ms": 211}),
            {"latency_ms": 211},
        )
        with self.assertRaises(ValueError):
            orchestrator._normalise_parameters("packet_loss", {"packet_loss_percent": 75})
        with self.assertRaises(ValueError):
            orchestrator._normalise_parameters("cpu", {"cpu_percent": 10, "cpuPercent": 20})

    def test_api_rejects_foreign_origin_and_remote_target(self):
        client = TestClient(orchestrator.app, base_url="http://127.0.0.1")
        self.assertEqual(client.get("/state", headers={"Origin": "https://example.org"}).status_code, 403)
        foreign_host = TestClient(network_info.app, base_url="http://example.org")
        self.assertEqual(foreign_host.get("/").status_code, 400)
        response = client.post(
            "/experiments",
            json={"failure_type": "cpu", "target_container": "other-host", "parameters": {}},
        )
        self.assertEqual(response.status_code, 422)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.db = {"experiments": MagicMock()}
        self.db["experiments"].find_one.return_value = {
            "experiment_id": "exp-1", "failure_type": "cpu", "status": "running",
        }
        self.machine = MagicMock()

    def test_failed_reset_does_not_mark_experiment_complete(self):
        with (patch.object(orchestrator, "_get_mongo", return_value=self.db),
              patch.object(orchestrator, "_get_redis"),
              patch.object(orchestrator, "StateMachine", return_value=self.machine),
              patch.object(orchestrator, "_call_reset", return_value={"error": "tc reset failed"}),
              patch.object(orchestrator, "_upsert_experiment") as upsert,
              patch.object(orchestrator, "_log_event")):
            with self.assertRaises(HTTPException) as error:
                orchestrator.stop_experiment("exp-1")
            self.assertEqual(error.exception.status_code, 502)
            upsert.assert_not_called()
            self.machine.transition.assert_any_call("running", experiment_id="exp-1")

    def test_successful_reset_marks_experiment_complete(self):
        with (patch.object(orchestrator, "_get_mongo", return_value=self.db),
              patch.object(orchestrator, "_get_redis"),
              patch.object(orchestrator, "StateMachine", return_value=self.machine),
              patch.object(orchestrator, "_call_reset", return_value={"message": "stopped"}),
              patch.object(orchestrator, "_upsert_experiment") as upsert,
              patch.object(orchestrator, "_log_event")):
            response = orchestrator.stop_experiment("exp-1")
            self.assertEqual(response["status"], "completed")
            self.assertEqual(upsert.call_args.args[2]["status"], "completed")
            self.machine.transition.assert_any_call("complete")

    def test_start_passes_selected_parameters_to_injection(self):
        self.db["experiments"].find_one.return_value = {
            "experiment_id": "exp-1", "failure_type": "cpu", "status": "created",
            "parameters": {"cpu_percent": 27, "duration_seconds": 12},
        }
        self.machine.get.return_value = "idle"
        with (patch.object(orchestrator, "_get_mongo", return_value=self.db),
              patch.object(orchestrator, "_get_redis"),
              patch.object(orchestrator, "StateMachine", return_value=self.machine),
              patch.object(orchestrator, "_call_injection", return_value={"started": True}) as inject,
              patch.object(orchestrator, "_upsert_experiment"),
              patch.object(orchestrator, "_log_event")):
            response = orchestrator.start_experiment("exp-1", orchestrator.StartExperimentRequest())
            inject.assert_called_once_with("cpu", {"cpu_percent": 27, "duration_seconds": 12})
            self.assertEqual(response["parameters"]["cpu_percent"], 27)

    def test_natural_finish_uses_normal_stop(self):
        tracker = metrics_writer.StateTracker()
        tracker.last_state = "running"
        tracker.active_experiment_id = "exp-1"
        with (patch.object(metrics_writer, "upsert_experiment"),
              patch.object(metrics_writer, "log_event"),
              patch.object(metrics_writer, "fetch_json", return_value={
                  "state": "running", "active_experiment_id": "exp-1"}),
              patch("requests.post") as post):
            tracker.handle_state(MagicMock(), "idle", [])
            self.assertTrue(post.call_args.args[0].endswith("/experiments/exp-1/stop"))

    def test_short_experiment_finishes_when_running_poll_was_missed(self):
        tracker = metrics_writer.StateTracker()
        with (patch.object(metrics_writer, "fetch_json", return_value={
                  "state": "running", "active_experiment_id": "exp-1"}),
              patch.object(metrics_writer.requests, "post") as post):
            tracker.handle_state(MagicMock(), "complete", [])
            self.assertTrue(post.call_args.args[0].endswith("/experiments/exp-1/stop"))

    def test_failed_natural_reset_keeps_running_record(self):
        tracker = metrics_writer.StateTracker()
        tracker.last_state = "running"
        tracker.active_experiment_id = "exp-1"
        with (patch.object(metrics_writer, "fetch_json", return_value={
                  "state": "running", "active_experiment_id": "exp-1"}),
              patch.object(metrics_writer.requests, "post") as post,
              patch.object(metrics_writer, "upsert_experiment") as upsert):
            post.return_value.raise_for_status.side_effect = requests.HTTPError("reset failed")
            tracker.handle_state(MagicMock(), "complete", [])
            upsert.assert_not_called()
            self.assertEqual(tracker.active_experiment_id, "exp-1")

    def test_emergency_stop_reports_active_reset_failure(self):
        self.machine.get_active_experiment.return_value = "exp-1"

        def response(url, timeout):
            result = MagicMock()
            result.status_code = 500 if "/reset/cpu" in url else 200
            result.json.return_value = {"detail": "reset failed"} if result.status_code == 500 else {"message": "reset"}
            if result.status_code == 500:
                result.raise_for_status.side_effect = requests.HTTPError("reset failed")
            return result

        with (patch.object(orchestrator, "_get_mongo", return_value=self.db),
              patch.object(orchestrator, "_get_redis"),
              patch.object(orchestrator, "StateMachine", return_value=self.machine),
              patch.object(orchestrator.requests, "post", side_effect=response),
              patch.object(orchestrator, "_upsert_experiment") as upsert):
            result = orchestrator.emergency_stop()
            self.assertEqual(result["status"], "partial_failure")
            upsert.assert_not_called()
            self.machine.force_idle.assert_not_called()


class NetworkRuleTests(unittest.TestCase):
    def locked(self, state):
        @contextmanager
        def context():
            yield state
        return context()

    def test_other_network_rule_is_not_overwritten(self):
        state = {"kind": "latency", "interface": "eth0", "value": 100}
        with (patch.object(network_rules, "network_interface", return_value="eth0"),
              patch.object(network_rules, "_locked_state", side_effect=lambda: self.locked(state)),
              patch.object(network_rules, "_netem_active", return_value=True),
              patch.object(network_rules.subprocess, "run") as run):
            with self.assertRaises(network_rules.NetworkRuleError):
                network_rules.apply_rule("packet_loss", 10)
            run.assert_not_called()

    def test_rule_command_and_reset_are_scoped(self):
        state = {}
        with (patch.object(network_rules, "network_interface", return_value="eth0"),
              patch.object(network_rules, "_locked_state", side_effect=lambda: self.locked(state)),
              patch.object(network_rules, "_netem_active", side_effect=[False, True]),
              patch.object(network_rules.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run):
            network_rules.apply_rule("latency", 240)
            self.assertEqual(state["kind"], "latency")
            self.assertIn("240ms", run.call_args.args[0])
            network_rules.reset_rule("latency")
            self.assertEqual(state, {})

    def test_non_owner_cannot_reset_active_rule(self):
        state = {"kind": "packet_loss", "interface": "eth0"}
        with (patch.object(network_rules, "network_interface", return_value="eth0"),
              patch.object(network_rules, "_locked_state", return_value=self.locked(state)),
              patch.object(network_rules, "_netem_active", return_value=True)):
            with self.assertRaises(network_rules.NetworkRuleError):
                network_rules.reset_rule("latency")


class MonitoringTests(unittest.TestCase):
    def test_throughput_uses_counters_without_downloading(self):
        network_info._throughput_sample = None
        network_info._throughput_kbps = 0
        with (patch.object(network_info.time, "monotonic", side_effect=[10, 11]),
              patch.object(network_info.psutil, "net_io_counters", side_effect=[
                  SimpleNamespace(bytes_sent=1000, bytes_recv=1000),
                  SimpleNamespace(bytes_sent=2000, bytes_recv=2000),
              ])):
            self.assertEqual(network_info.get_network_throughput(), 0)
            self.assertEqual(network_info.get_network_throughput(), 16)


class InstallerTests(unittest.TestCase):
    def test_config_generation_creates_and_preserves_private_credentials(self):
        script = (ROOT / "install_dsfst.sh").read_text(encoding="utf-8")
        config_block = script.split(".venv/bin/python - <<'PY'\n", 1)[1].split("\nPY", 1)[0]
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / ".dsfst").mkdir()
            (folder / "database").mkdir()
            shutil.copyfile(ROOT / "database" / "sample_data.py", folder / "database" / "sample_data.py")
            shutil.copyfile(ROOT / ".gitignore", folder / ".gitignore")
            try:
                os.chdir(folder)
                exec(config_block, {})
                first = dotenv_values(".env")
                self.assertNotEqual(first["MONGO_PASSWORD"], "test1234")
                self.assertNotEqual(first["REDIS_PASSWORD"], "test1234")
                self.assertNotEqual(first["INFLUX_PASSWORD"], "test1234")
                self.assertIn(first["MONGO_PASSWORD"], first["MONGO_URI"])
                exec(config_block, {})
                self.assertEqual(first, dotenv_values(".env"))
                redis_block = script.split(".venv/bin/python - <<'PY'\n")[2].split("\nPY", 1)[0]
                exec(redis_block, {})
                self.assertIn(first["REDIS_PASSWORD"], (folder / ".dsfst" / "redis.conf").read_text())
            finally:
                os.chdir(original_cwd)

    def test_generated_compose_uses_private_ports_and_credentials(self):
        script = (ROOT / "install_dsfst.sh").read_text(encoding="utf-8")
        compose = script.split("cat > .dsfst/compose.yaml <<'YAML'\n", 1)[1].split("\nYAML", 1)[0]
        services = yaml.safe_load(compose)["services"]
        self.assertEqual(set(services), {"mongodb", "influxdb", "redis"})
        for service in services.values():
            self.assertEqual(service["ports"][0]["host_ip"], "127.0.0.1")
            self.assertNotIn("published", service["ports"][0])
        self.assertIn("MONGO_PASSWORD", services["mongodb"]["environment"]["MONGO_INITDB_ROOT_PASSWORD"])
        self.assertIn("INFLUX_PASSWORD", services["influxdb"]["environment"]["DOCKER_INFLUXDB_INIT_PASSWORD"])
        self.assertIn("REDIS_PASSWORD", services["redis"]["environment"]["REDIS_PASSWORD"])
        legacy_services = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
        for service in legacy_services.values():
            self.assertEqual(service["ports"][0]["host_ip"], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
