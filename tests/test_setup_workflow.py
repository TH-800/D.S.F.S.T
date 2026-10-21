"""Run the actual setup entry point with fake host commands in a temporary folder."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASH = (r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else shutil.which("bash"))


@unittest.skipUnless(BASH and Path(BASH).exists(), "Bash is required for the setup workflow test")
@unittest.skipIf(hasattr(os, "getuid") and os.getuid() == 0, "Setup deliberately refuses the root user")
class SetupWorkflowTests(unittest.TestCase):
    def run_setup(self, **options):
        with tempfile.TemporaryDirectory(prefix="dsfst-setup-") as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            (root / ".dsfst").mkdir()
            (root / ".dsfst/addresses.txt").write_text("http://localhost:3000\n", encoding="utf-8")
            shutil.copyfile(ROOT / "setup_dsfst.sh", root / "setup_dsfst.sh")
            scripts = {
                "bin/systemctl": '[[ "${ACTIVE:-0}" == 1 ]]',
                "bin/sudo": 'printf "sudo %s\\n" "$*" >> events.txt',
                "bin/python3": 'printf "probe %s\\n" "$*" >> events.txt\nif [[ "$*" == *--check-idle* ]]; then exit "${IDLE_RESULT:-0}"; else exit "${READY_RESULT:-0}"; fi',
                "bin/VBoxControl": "exit 1",
                "install_dsfst.sh": 'printf "install\\n" >> events.txt\nexit "${INSTALL_RESULT:-0}"',
                "enable_dsfst_autostart.sh": 'printf "autostart\\n" >> events.txt',
            }
            for relative, contents in scripts.items():
                path = root / relative
                path.write_text("#!/usr/bin/env bash\n" + contents + "\n", encoding="utf-8")
                path.chmod(0o755)
            result = subprocess.run([BASH, "-c", 'export PATH="$PWD/bin:$PATH"; exec bash setup_dsfst.sh'],
                                    cwd=root, env={**os.environ, **{key: str(value) for key, value in options.items()}},
                                    capture_output=True, text=True, timeout=20)
            log = root / "events.txt"
            return result, log.read_text().splitlines() if log.exists() else []

    def test_install_start_and_readiness_are_required_for_success(self):
        result, events = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["install", "autostart", "sudo systemctl restart dsfst.service",
                                  "probe dsfst_readiness.py --timeout 720"])
        self.assertIn("Full setup complete", result.stdout)

    def test_active_work_refusal_does_not_stop_or_modify_services(self):
        result, events = self.run_setup(ACTIVE=1, IDLE_RESULT=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ["probe dsfst_readiness.py --check-idle"])
        self.assertNotIn("Full setup complete", result.stdout)

    def test_existing_idle_service_is_checked_before_upgrade(self):
        result, events = self.run_setup(ACTIVE=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events[:3], ["probe dsfst_readiness.py --check-idle", "sudo systemctl stop dsfst.service", "install"])

    def test_install_failure_aborts_before_service_start(self):
        result, events = self.run_setup(INSTALL_RESULT=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ["install"])
        self.assertNotIn("Full setup complete", result.stdout)

    def test_readiness_failure_never_reports_success(self):
        result, events = self.run_setup(READY_RESULT=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("probe dsfst_readiness.py --timeout 720", events)
        self.assertNotIn("Full setup complete", result.stdout)
