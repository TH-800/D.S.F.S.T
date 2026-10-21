"""Exercise setup checks through a real HTTP fixture, without installing services."""
import copy
import io
import json
import subprocess
import sys
import threading
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dsfst_readiness as readiness


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.paths = []
        self.statuses = {}
        timestamp = datetime.now(timezone.utc).isoformat()
        self.bodies = {
            "/": '<html><div id="root"></div></html>',
            "/api/8009/state": {"state": "idle", "active_experiment_id": None},
            "/api/8009/vms": [{"vm_id": "local"}],
            "/api/8009/experiment-batches?active_only=true&limit=50": [],
            "/api/8008/metrics/latest": {
                "vm_id": "local", "cpu": {"cpu_usage_percent": 20, "timestamp": timestamp},
                "memory": {"memory_used_mb": 800, "memory_percent": 40, "timestamp": timestamp},
                "network": {"latency_ms": 2, "packet_loss_percent": 0, "throughput_kbps": 12, "timestamp": timestamp},
            },
        }
        for port in range(8001, 8008):
            self.bodies[f"/api/{port}/"] = {"message": "API ready"}
        for port, service in ((8000, "ExperimentMonitor"), (8008, "metrics_api"),
                              (8009, "experiment_orchestrator"), (8010, "reports_aggregator")):
            self.bodies[f"/api/{port}/health"] = {
                "status": "ok", "service": service, "mongo": "connected", "redis": "connected"}
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.paths.append(self.path)
                body = fixture.bodies.get(self.path, {})
                if callable(body):
                    body = body()
                self.send_response(fixture.statuses.get(self.path, 200))
                self.send_header("Content-Type", "text/html" if isinstance(body, str) else "application/json")
                self.end_headers()
                self.wfile.write((body if isinstance(body, str) else json.dumps(body)).encode())

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_full_stack_is_checked_through_the_gateway(self):
        readiness.check_ready(self.base)
        self.assertTrue(all(any(path.startswith(f"/api/{port}/") for path in self.paths)
                            for port in range(8000, 8011)))
        self.assertIn("/api/8009/vms", self.paths)
        self.assertIn("/api/8008/metrics/latest", self.paths)

    def test_one_unavailable_backend_prevents_setup_success(self):
        for path in list(self.bodies):
            if path.endswith("/health") or (path.startswith("/api/") and path.endswith("/")):
                with self.subTest(path=path):
                    self.statuses[path] = 503
                    with self.assertRaisesRegex(readiness.ReadinessError, path):
                        readiness.wait_until_ready(self.base, timeout=0)
                    self.statuses.clear()

    def test_database_failures_block_readiness(self):
        for port, database in ((8009, "mongo"), (8009, "redis"), (8010, "mongo")):
            health = self.bodies[f"/api/{port}/health"]
            with self.subTest(port=port, database=database):
                health[database] = "unreachable"
                with self.assertRaises(readiness.ReadinessError):
                    readiness.check_ready(self.base)
                health[database] = "connected"

    def test_stale_missing_or_invalid_metrics_block_readiness(self):
        metrics = self.bodies["/api/8008/metrics/latest"]
        original = copy.deepcopy(metrics)
        for change in (None, {"cpu_usage_percent": "high", "timestamp": "now"},
                       {"cpu_usage_percent": True, "timestamp": "now"},
                       {"cpu_usage_percent": 10 ** 400, "timestamp": datetime.now(timezone.utc).isoformat()},
                       {"cpu_usage_percent": 2, "timestamp": "2026-10-15T12:00:00"},
                       {"cpu_usage_percent": 2, "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()},
                       {"cpu_usage_percent": 2, "timestamp": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}):
            with self.subTest(sample=change):
                metrics["cpu"] = change
                with self.assertRaises(readiness.ReadinessError):
                    readiness.check_ready(self.base)
        self.bodies["/api/8008/metrics/latest"] = original

    def test_startup_wait_recovers_when_a_backend_becomes_ready(self):
        def first_check():
            self.bodies["/api/8000/health"] = {"status": "ok", "service": "ExperimentMonitor"}
            return {"status": "starting", "service": "ExperimentMonitor"}
        self.bodies["/api/8000/health"] = first_check
        with redirect_stdout(io.StringIO()):
            readiness.wait_until_ready(self.base, timeout=2, interval=0)
        self.assertEqual(self.paths.count("/api/8000/health"), 2)

    def test_upgrade_guard_refuses_active_and_unknown_states(self):
        path = "/api/8009/experiment-batches?active_only=true&limit=50"
        readiness.ensure_idle(self.base)
        for state in ("running", "stopping", "unknown"):
            self.bodies["/api/8009/state"]["state"] = state
            with self.subTest(state=state), self.assertRaises(readiness.ReadinessError):
                readiness.ensure_idle(self.base)
        self.bodies["/api/8009/state"]["state"] = "idle"
        for status in ("starting", "running", "partial_failure", "stopping", "unknown"):
            self.bodies[path] = [{"status": status}]
            with self.subTest(batch=status), self.assertRaises(readiness.ReadinessError):
                readiness.ensure_idle(self.base)
        self.bodies[path] = []
        self.statuses[path] = 404
        readiness.ensure_idle(self.base)  # Allow upgrades from versions without batches.
        self.statuses[path] = 503
        with self.assertRaises(OSError):
            readiness.ensure_idle(self.base)

    def test_cli_checks_cannot_be_disabled_by_python_optimization(self):
        self.bodies["/api/8009/health"]["redis"] = "unreachable"
        result = subprocess.run([sys.executable, "-O", str(ROOT / "dsfst_readiness.py"),
                                 "--base-url", self.base, "--timeout", "0"],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Redis", result.stderr)
        self.assertIn("journalctl", result.stderr)


if __name__ == "__main__":
    unittest.main()
