"""Exercise Linux flock and state persistence without running system commands."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "InjectionScripts"))
import network_rules


with tempfile.TemporaryDirectory() as temp:
    state_dir = Path(temp)
    with (patch.object(network_rules, "STATE_DIR", state_dir),
          patch.object(network_rules, "network_interface", return_value="eth0"),
          patch.object(network_rules, "_netem_active", side_effect=[False, True]),
          patch.object(network_rules.subprocess, "run") as run):
        run.return_value.returncode = 0
        network_rules.apply_rule("latency", 125)
        assert json.loads((state_dir / "network-rule.json").read_text())["kind"] == "latency"
        network_rules.reset_rule("latency")
        assert json.loads((state_dir / "network-rule.json").read_text()) == {}

print("Linux network lock smoke test passed")
