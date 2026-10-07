"""Launcher regressions: slow VM imports and cleanup of incomplete stacks."""
import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import RunALL as launcher


class LauncherTests(unittest.TestCase):
    def child(self, code="import time; time.sleep(60)"):
        process = subprocess.Popen([sys.executable, "-c", code],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        self.addCleanup(cleanup)
        return process

    def test_slow_service_gets_time_to_bind(self):
        process = MagicMock()
        process.poll.return_value = None
        with (patch.object(launcher.subprocess, "Popen", return_value=process),
              patch.object(launcher.threading, "Thread"),
              patch.object(launcher, "port_in_use", side_effect=[False, False, True]),
              patch.object(launcher.time, "monotonic", side_effect=[0, 0, 9]),
              patch.object(launcher.time, "sleep"),
              contextlib.redirect_stdout(io.StringIO())):
            actual = launcher.start_fastapi_service(
                {"name":"slow VM service","module":"app:app","port":8000,"cwd":"."})
        self.assertIs(actual, process)
        process.terminate.assert_not_called()

    def test_missing_backend_aborts_and_terminates_owned_process(self):
        process = self.child()
        services = [{"name":"working"},{"name":"broken"}]
        with (patch.object(launcher, "SERVICES", services),
              patch.object(launcher, "running_processes", []),
              patch.object(launcher.signal, "signal"),
              patch.object(launcher, "start_fastapi_service", side_effect=[process, None]),
              patch.object(launcher, "start_frontend") as frontend,
              patch.object(launcher.time, "sleep"),
              contextlib.redirect_stdout(io.StringIO())):
            with self.assertRaises(SystemExit) as error:
                launcher.main()
        self.assertEqual(error.exception.code, 1)
        self.assertIsNotNone(process.poll())
        frontend.assert_not_called()

    def test_backend_exit_stops_remaining_stack(self):
        exited = self.child("pass")
        exited.wait(timeout=5)
        frontend = self.child()
        with (patch.object(launcher, "SERVICES", [{"name":"exited backend"}]),
              patch.object(launcher, "running_processes", []),
              patch.object(launcher.signal, "signal"),
              patch.object(launcher, "start_fastapi_service", return_value=exited),
              patch.object(launcher, "start_frontend", return_value=frontend),
              patch.object(launcher.time, "sleep"),
              contextlib.redirect_stdout(io.StringIO())):
            with self.assertRaises(SystemExit) as error:
                launcher.main()
        self.assertEqual(error.exception.code, 1)
        self.assertIsNotNone(frontend.poll())


if __name__ == "__main__":
    unittest.main()
