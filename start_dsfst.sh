#!/usr/bin/env bash
# Put beside RunALL.py. Start only; run install_dsfst.sh once beforehand.
# Ctrl+C stops this app's process groups. Database containers and data are kept.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
ROOT="$PWD"
[[ -f .dsfst/install-complete && -f .venv/bin/activate ]] || {
    echo 'Installation is incomplete. Run: bash install_dsfst.sh && bash start_dsfst.sh' >&2
    exit 1
}
source .venv/bin/activate
export PATH="$VIRTUAL_ENV/bin:/usr/sbin:/sbin:$PATH"
export PYTHONUNBUFFERED=1 PORT=3000

# Prevent a second launcher from attaching to the same app or starting another writer.
exec 9>.dsfst/running.lock
flock -n 9 || { echo 'D.S.F.S.T is already running through this launcher.' >&2; exit 1; }
export DSFST_INTERFACE
DSFST_INTERFACE="$(ip -o route show default | awk '{for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')"
[[ -n "$DSFST_INTERFACE" ]] || { echo 'No default network interface found.' >&2; exit 1; }
[[ "$DSFST_INTERFACE" == "$(cat .dsfst/interface)" ]] || {
    echo 'The network interface changed. Rerun install_dsfst.sh to update its sudo permissions.' >&2
    exit 1
}

# RunALL.py otherwise silently skips occupied ports, potentially using unrelated services.
python - <<'PY'
import socket
for port in [3000, *range(8000, 8011)]:
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', port))
PY

sudo -v
sudo systemctl start docker
sudo modprobe sch_netem
compose=(sudo docker compose --project-name dsfst-vm --project-directory "$ROOT"
    --env-file "$ROOT/.env" -f "$ROOT/.dsfst/compose.yaml")
"${compose[@]}" up -d --wait --wait-timeout 180 --pull never

# Use Docker's actual port assignments, leaving other database services alone.
MONGO_ADDRESS="$("${compose[@]}" port mongodb 27017)"
INFLUX_ADDRESS="$("${compose[@]}" port influxdb 8086)"
REDIS_ADDRESS="$("${compose[@]}" port redis 6379)"
export MONGO_URI="mongodb://test1234:test1234@${MONGO_ADDRESS}/?authSource=admin"
export INFLUXDB_URL="http://${INFLUX_ADDRESS}"
export REDIS_PORT="${REDIS_ADDRESS##*:}"
python - <<'PY'
import os
from dotenv import set_key

for name in ('.env', 'database/.env'):
    for key in ('MONGO_URI', 'INFLUXDB_URL', 'REDIS_PORT'):
        set_key(name, key, os.environ[key], quote_mode='always')
    os.chmod(name, 0o600)
PY
printf 'Dashboard: http://localhost:3000/#/\nInfluxDB: %s\n' "$INFLUXDB_URL" > .dsfst/addresses.txt
(cd database && "$ROOT/.venv/bin/python" mongo_setup.py && "$ROOT/.venv/bin/python" influx_setup.py)

pids=()
cleanup() {
    trap '' INT TERM
    # Undo active experiments before shutting down their APIs.
    curl -fsS --max-time 22 -X POST http://127.0.0.1:8009/emergency-stop >/dev/null 2>&1 || true
    for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
    for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# RunALL starts all 11 APIs and the frontend. A separate process group includes
# its npm/node children so they are not left behind when this launcher stops.
setsid python -u RunALL.py &
pids+=("$!")

# Wait for startup, rather than assuming a fixed sleep is enough on every VM.
python - <<'PY'
import socket
import time

deadline = time.monotonic() + 120
for port in [*range(8000, 8011), 3000]:
    while True:
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                break
        if time.monotonic() >= deadline:
            raise SystemExit(f'Service on port {port} did not start. See its output above.')
        time.sleep(0.3)
PY

setsid python -u metrics_writer.py &
pids+=("$!")
printf '\n'
cat .dsfst/addresses.txt
printf 'Press Ctrl+C to stop the app.\n'
wait -n "${pids[@]}"
