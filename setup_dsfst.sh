#!/usr/bin/env bash
# One command installs/configures the full stack and enables/starts its service.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
[[ "$EUID" != 0 && "$PWD" != *' '* ]] || {
    echo 'Run as your normal Ubuntu user from a project path without spaces.' >&2
    exit 1
}
# Refuse an upgrade that would interrupt an active experiment on any registered VM.
if systemctl is-active --quiet dsfst.service; then
    python3 - <<'PY'
import json
import urllib.request
state = json.load(urllib.request.urlopen('http://127.0.0.1:8009/state', timeout=5))
if state.get('active_experiment_id') or state.get('state') not in ('idle', 'complete'):
    raise SystemExit('Finish or stop the active experiment before setup.')
try:
    batches = json.load(urllib.request.urlopen('http://127.0.0.1:8009/experiment-batches?active_only=true&limit=50', timeout=60))
except urllib.error.HTTPError as error:
    if error.code != 404:
        raise
else:
    if any(b['status'] in ('starting', 'running', 'partial_failure', 'stopping') for b in batches):
        raise SystemExit('Finish or stop active multi-VM batches before setup.')
PY
    sudo systemctl stop dsfst.service
fi
bash install_dsfst.sh
bash enable_dsfst_autostart.sh
if command -v VBoxControl >/dev/null && VBoxControl guestproperty get /DSFST/HostOnlyIP 2>/dev/null | grep -q '^Value: 192\.168\.56\.'; then
    sudo bash configure_dsfst_network.sh --install
fi
sudo systemctl restart dsfst.service
python3 - <<'PY'
import json
import time
import urllib.request
from datetime import datetime, timezone
# The launcher allows 240s for databases and 420s for API/frontend startup.
deadline = time.monotonic() + 720
while True:
    try:
        with urllib.request.urlopen('http://127.0.0.1:3000/', timeout=5) as response:
            assert response.status == 200
        with urllib.request.urlopen('http://127.0.0.1:8009/state', timeout=5) as response:
            assert json.load(response)['state'] in ('idle', 'complete')
        with urllib.request.urlopen('http://127.0.0.1:8009/health', timeout=5) as response:
            health = json.load(response)
            assert health.get('mongo') == health.get('redis') == 'connected'
        with urllib.request.urlopen('http://127.0.0.1:8008/metrics/latest', timeout=5) as response:
            readings = json.load(response)
            now = datetime.now(timezone.utc)
            for key in ('cpu', 'memory', 'network'):
                sample = readings[key]
                timestamp = datetime.fromisoformat(sample['timestamp'].replace('Z', '+00:00'))
                assert -10 <= (now - timestamp).total_seconds() <= 60
        break
    except Exception:
        if time.monotonic() > deadline:
            raise SystemExit('Startup did not become ready. Check journalctl -u dsfst.service.')
        time.sleep(3)
PY
echo 'Full setup complete: databases, APIs, dashboard and metrics writer are ready.'
cat .dsfst/addresses.txt
