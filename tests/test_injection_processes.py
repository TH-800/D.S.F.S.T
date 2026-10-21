"""Reset must stop this injection's workers and preserve a failed reset for retry."""
import os
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import psutil
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "InjectionScripts"))
import process_control
import CPUStressInjection as cpu
import MemoryStressInjection as memory


class ProcessResetTests(unittest.TestCase):
    def process(self):
        return SimpleNamespace(pid=123, poll=MagicMock(return_value=None), wait=MagicMock())

    def test_reset_signals_only_the_owned_group_and_waits_for_workers(self):
        process = self.process()
        child = MagicMock()
        with (patch.object(process_control.os, "getpgid", create=True, return_value=123),
              patch.object(process_control.os, "killpg", create=True) as kill_group,
              patch.object(process_control.psutil, "Process") as lookup,
              patch.object(process_control.psutil, "wait_procs", return_value=([child], [])) as wait):
            lookup.return_value.children.return_value = [child]
            self.assertTrue(process_control.stop_owned_process(process))
            kill_group.assert_called_once_with(123, signal.SIGTERM)
            wait.assert_any_call([child], timeout=2)
            process.wait.assert_called_once_with(timeout=2)

    def test_reset_refuses_a_group_not_owned_by_the_injection(self):
        with (patch.object(process_control.os, "getpgid", create=True, return_value=999),
              patch.object(process_control.os, "killpg", create=True) as kill_group):
            with self.assertRaises(RuntimeError):
                process_control.stop_owned_process(self.process())
            kill_group.assert_not_called()

    def test_unresponsive_master_is_killed_before_success_is_reported(self):
        process = self.process()
        process.wait.side_effect = [subprocess.TimeoutExpired("stress-ng", 2), None]
        with (patch.object(process_control.os, "getpgid", create=True, return_value=123),
              patch.object(process_control.os, "killpg", create=True) as kill_group,
              patch.object(process_control.psutil, "Process") as lookup,
              patch.object(process_control.psutil, "wait_procs", return_value=([], []))):
            lookup.return_value.children.return_value = []
            self.assertTrue(process_control.stop_owned_process(process))
            self.assertEqual(kill_group.call_args_list[-1].args, (123, getattr(signal, "SIGKILL", 9)))
            self.assertEqual(process.wait.call_count, 2)

    def test_failed_reset_keeps_the_process_handle_for_retry(self):
        for module, attribute, reset in ((cpu, "cpu_process", cpu.reset_cpu_stress),
                                          (memory, "memory_process", memory.reset_memory_stress)):
            process = self.process()
            with self.subTest(injection=attribute), patch.object(module, attribute, process), \
                 patch.object(module, "stop_owned_process", side_effect=RuntimeError("Worker still running")):
                with self.assertRaises(HTTPException) as error:
                    reset()
                self.assertEqual(error.exception.status_code, 502)
                self.assertIs(getattr(module, attribute), process)

    def test_both_injectors_start_a_separate_process_group(self):
        for module, attribute, start in ((cpu, "cpu_process", lambda: cpu.inject_cpu_stress(10, 15)),
                                        (memory, "memory_process", lambda: memory.inject_memory_stress(128, 15))):
            with self.subTest(injection=attribute), patch.object(module, attribute, None), \
                 patch.object(module.subprocess, "Popen") as launch:
                start()
                self.assertTrue(launch.call_args.kwargs["start_new_session"])

    @unittest.skipUnless(os.name == "posix", "A real process group requires Linux")
    def test_real_worker_ignoring_termination_does_not_survive_reset(self):
        child_code = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('ready',flush=True);time.sleep(60)"
        parent_code = ("import subprocess,sys,time;child=subprocess.Popen([sys.executable,'-c'," + repr(child_code) +
                       "],stdout=subprocess.PIPE);child.stdout.readline();print(child.pid,flush=True);time.sleep(60)")
        process = subprocess.Popen([sys.executable, "-c", parent_code], start_new_session=True,
                                   stdout=subprocess.PIPE, text=True)
        child = None
        try:
            child = psutil.Process(int(process.stdout.readline()))
            self.assertTrue(process_control.stop_owned_process(process))
            self.assertFalse(process_control._running(child))
            self.assertIsNotNone(process.poll())
        finally:
            for item in ([child] if child else []) + [psutil.Process(process.pid) if process.poll() is None else None]:
                if item and process_control._running(item):
                    item.kill()
            process.wait(timeout=5)
            process.stdout.close()
