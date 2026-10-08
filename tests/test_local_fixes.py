"""Regressions for fixes carried from Momin's Ubuntu diff; no stress is run."""
import sys
import signal
import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'InjectionScripts'))
import CPUStressInjection as cpu
import MemoryStressInjection as memory
import metrics_writer
from fastapi import HTTPException


class LocalFixTests(unittest.TestCase):
    def test_cpu_passes_load_and_reaps_child(self):
        with patch.object(cpu, 'cpu_process', None), patch.object(cpu.os, 'cpu_count', return_value=4), patch.object(cpu.subprocess, 'Popen') as popen, patch.object(cpu.threading, 'Thread') as thread:
            result = cpu.inject_cpu_stress(25, 15)
            self.assertNotIn('error', result)
            command = popen.call_args.args[0]
            self.assertEqual(command[command.index('--cpu') + 1], '4')
            self.assertEqual(command[command.index('--cpu-load') + 1], '25')
            self.assertEqual(command[command.index('--timeout') + 1], '15s')
            thread.assert_called_once_with(target=popen.return_value.wait, daemon=True)
            thread.return_value.start.assert_called_once()

    def test_memory_guard_blocks_unsafe_allocation(self):
        with patch.object(memory, 'memory_process', None), patch.object(memory.psutil, 'virtual_memory', return_value=SimpleNamespace(available=600 * 1024 * 1024)), patch.object(memory.subprocess, 'Popen') as popen:
            self.assertIn('error', memory.inject_memory_stress(512, 10))
            popen.assert_not_called()

    def test_memory_starts_own_group_and_reaps(self):
        with patch.object(memory, 'memory_process', None), patch.object(memory.psutil, 'virtual_memory', return_value=SimpleNamespace(available=2048 * 1024 * 1024)), patch.object(memory.subprocess, 'Popen') as popen, patch.object(memory.threading, 'Thread') as thread:
            self.assertNotIn('error', memory.inject_memory_stress(128, 10))
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            thread.return_value.start.assert_called_once()

    def test_memory_reset_escalates_only_its_group(self):
        proc = MagicMock(pid=12345)
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired('stress-ng', 5), None]
        with patch.object(memory, 'memory_process', proc), patch.object(memory.os, 'killpg') as killpg:
            self.assertEqual(memory.reset_memory_stress()['message'], 'Memory stress stopped')
            self.assertEqual([call.args for call in killpg.call_args_list], [(12345, signal.SIGTERM), (12345, signal.SIGKILL)])
            self.assertIsNone(memory.memory_process)

    def test_failed_reset_keeps_process_reference(self):
        proc = MagicMock(pid=12345)
        proc.poll.return_value = None
        with patch.object(memory, 'memory_process', proc), patch.object(memory.os, 'killpg', side_effect=PermissionError()):
            with self.assertRaises(HTTPException) as error:
                memory.reset_memory_stress()
            self.assertEqual(error.exception.status_code, 502)
            self.assertIs(memory.memory_process, proc)

    def test_metrics_keep_collection_time(self):
        timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for method in [metrics_writer.write_cpu_metric, metrics_writer.write_memory_metric, metrics_writer.write_network_metric]:
            writer = MagicMock()
            method(writer, {'_collected_at': timestamp})
            point = writer.write.call_args.kwargs['record']
            self.assertTrue(point.to_line_protocol().endswith('1577836800000000000'))

    def test_fetch_stamps_collection_time(self):
        with patch.object(metrics_writer.requests, 'get') as get:
            get.return_value.json.return_value = {'cpu_usage_percent': 25}
            result = metrics_writer.fetch_json('http://localhost/test')
            self.assertEqual(result['cpu_usage_percent'], 25)
            self.assertIsInstance(result['_collected_at'], datetime)
