#!/usr/bin/env bash
# Run once, as your normal user, on an Ubuntu x86-64 VM.
# Put this script beside RunALL.py. Installs/configures only; does not start the app.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
ROOT="$PWD"

. /etc/os-release
if [[ "$ID" != ubuntu || "$(uname -m)" != x86_64 || "$EUID" == 0 ]]; then
    echo 'Run as your normal user on an Ubuntu x86-64 VM, without sudo before bash.' >&2
    exit 1
fi
if ! grep -qw avx /proc/cpuinfo; then
    echo 'MongoDB requires AVX. Enable CPU/AVX passthrough in the VM configuration.' >&2
    exit 1
fi
[[ -f RunALL.py ]] || { echo 'Place both scripts beside RunALL.py.' >&2; exit 1; }
rm -f .dsfst/install-complete
sudo -v

# Remove only repository entries created by the previous version of this installer.
# Keep existing Docker/NodeSource entries and their signing keys unchanged.
sudo rm -f /etc/apt/sources.list.d/dsfst-docker.list \
    /etc/apt/sources.list.d/dsfst-node.list

# Linux commands used by the app, and tools needed to install its dependencies.
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-dev build-essential \
    ca-certificates curl gnupg iproute2 iputils-ping stress-ng procps util-linux kmod
# Minimal/cloud kernels may package netem separately.
if ! modinfo sch_netem >/dev/null 2>&1; then
    sudo apt-get install -y "linux-modules-extra-$(uname -r)"
fi

# Ask APT for enabled repositories; this handles both .list and .sources files.
# Reuse existing entries instead of adding a conflicting Signed-By path.
REPO_URIS="$(apt-get indextargets --no-release-info --format '$(BASE_URI)')"
sudo install -m 0755 -d /etc/apt/keyrings
if [[ "$REPO_URIS" != *download.docker.com/linux/ubuntu/* ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        sudo tee /etc/apt/keyrings/dsfst-docker.asc >/dev/null
    sudo chmod 644 /etc/apt/keyrings/dsfst-docker.asc
    printf 'deb [arch=amd64 signed-by=/etc/apt/keyrings/dsfst-docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
        "$VERSION_CODENAME" | sudo tee /etc/apt/sources.list.d/dsfst-docker.list >/dev/null
fi
if [[ "$REPO_URIS" != *deb.nodesource.com/node_22.x/* ]]; then
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | \
        sudo gpg --dearmor --batch --yes -o /etc/apt/keyrings/dsfst-node.gpg
    sudo chmod 644 /etc/apt/keyrings/dsfst-node.gpg
    printf '%s\n' 'deb [arch=amd64 signed-by=/etc/apt/keyrings/dsfst-node.gpg] https://deb.nodesource.com/node_22.x nodistro main' | \
        sudo tee /etc/apt/sources.list.d/dsfst-node.list >/dev/null
fi
printf 'Package: nodejs\nPin: origin deb.nodesource.com\nPin-Priority: 600\n' | \
    sudo tee /etc/apt/preferences.d/dsfst-nodejs >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin nodejs
sudo systemctl enable --now docker

# All third-party Python imports, plus uvicorn used by RunALL.py.
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install \
    'fastapi>=0.115,<1' 'uvicorn>=0.30,<1' 'psutil>=6,<8' 'requests>=2.32,<3' \
    'pymongo>=4.10,<5' 'influxdb-client>=1.48,<2' 'python-dotenv>=1,<2' \
    'redis>=5,<6' 'pydantic>=2,<3'
(cd dsft-frontend && npm ci --include=dev --no-audit --no-fund)

# Save local configuration and the few compatibility fixes needed by this ZIP.
# Originals are preserved in .dsfst/originals; the existing Compose file is untouched.
umask 077
mkdir -p .dsfst
.venv/bin/python - <<'PY'
from pathlib import Path
import secrets
import shutil


def save(name, text):
    path = Path(name)
    backup = Path('.dsfst/originals') / name
    if path.exists() and path.read_text(encoding='utf-8') != text and not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    path.write_text(text, encoding='utf-8')


token_file = Path('.dsfst/influx-token')
if not token_file.exists():
    token_file.write_text(secrets.token_urlsafe(48), encoding='utf-8')
token_file.chmod(0o600)
env = f'''MONGO_URI=mongodb://test1234:test1234@127.0.0.1:27017/?authSource=admin
MONGO_DB_NAME=dsfst
INFLUXDB_URL=http://127.0.0.1:8086
INFLUXDB_TOKEN={token_file.read_text().strip()}
INFLUXDB_ORG=dsfst-org
INFLUXDB_BUCKET=dsfst-bucket
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_USERNAME=test1234
REDIS_PASSWORD=test1234
'''
for name in ('.env', 'database/.env'):
    save(name, env)
    Path(name).chmod(0o600)

# Both Redis connections (including the health check) must authenticate.
name = 'experiment_orchestrator.py'
text = Path(name).read_text(encoding='utf-8')
if 'username=os.getenv("REDIS_USERNAME")' not in text:
    text = text.replace('redis.Redis(', 'redis.Redis(username=os.getenv("REDIS_USERNAME"), password=os.getenv("REDIS_PASSWORD"), ')
save(name, text)

# Use the VM interface exported by the launcher and fix the undefined reset result.
for name in ('InjectionScripts/NetworkLatencyInjection.py', 'InjectionScripts/PacketLossInjection.py'):
    text = Path(name).read_text(encoding='utf-8')
    if '\nimport os\n' not in '\n' + text:
        text = 'import os\n' + text
    text = text.replace('NETWORK_INTERFACE = "ens33"', 'NETWORK_INTERFACE = os.environ.get("DSFST_INTERFACE", "ens33")')
    text = text.replace('    subprocess.run([\n', '    result = subprocess.run([\n')
    save(name, text)

# datetime.UTC is unavailable in Ubuntu 22.04's Python 3.10.
name = 'database/sample_data.py'
text = Path(name).read_text(encoding='utf-8').replace(
    'from datetime import datetime, UTC', 'from datetime import datetime, timezone\nUTC = timezone.utc')
save(name, text)

ignore = Path('.gitignore')
text = ignore.read_text(encoding='utf-8') if ignore.exists() else ''
for entry in ('.env', 'database/.env', '.venv/', '.dsfst/'):
    if entry not in text.splitlines():
        text = text.rstrip('\n') + '\n' + entry + '\n'
save('.gitignore', text)
PY

# Redis uses a named account, not an unauthenticated default account.
cat > .dsfst/redis.conf <<'CONF'
user default off
user test1234 on >test1234 ~* &* +@all
CONF
chmod 644 .dsfst/redis.conf

# Dedicated volumes avoid changing credentials in existing database volumes.
# Docker assigns free host ports, published only on the VM loopback interface.
cat > .dsfst/compose.yaml <<'YAML'
services:
  mongodb:
    image: mongo:6.0.13
    ports: [{target: 27017, host_ip: "127.0.0.1"}]
    environment:
      MONGO_INITDB_ROOT_USERNAME: test1234
      MONGO_INITDB_ROOT_PASSWORD: test1234
    volumes: ["mongodb_data:/data/db"]
    healthcheck:
      test: ["CMD-SHELL", "test \"$$(cat /proc/1/comm)\" = mongod && mongosh --quiet --username test1234 --password test1234 --authenticationDatabase admin --eval 'quit(db.adminCommand({ping:1}).ok ? 0 : 1)'"]
      interval: 2s
      timeout: 5s
      retries: 60
      start_period: 10s
  influxdb:
    image: influxdb:2.7
    ports: [{target: 8086, host_ip: "127.0.0.1"}]
    environment:
      DOCKER_INFLUXDB_INIT_MODE: setup
      DOCKER_INFLUXDB_INIT_USERNAME: test1234
      DOCKER_INFLUXDB_INIT_PASSWORD: test1234
      DOCKER_INFLUXDB_INIT_ORG: dsfst-org
      DOCKER_INFLUXDB_INIT_BUCKET: dsfst-bucket
      DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: ${INFLUXDB_TOKEN:?Missing InfluxDB token}
      INFLUXD_REPORTING_DISABLED: "true"
    volumes: ["influxdb_data:/var/lib/influxdb2", "influxdb_config:/etc/influxdb2"]
    healthcheck:
      test: ["CMD-SHELL", "test \"$$(cat /proc/1/comm)\" = influxd && influx bucket list --host http://127.0.0.1:8086 --org dsfst-org --token \"$$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN\" >/dev/null"]
      interval: 2s
      timeout: 5s
      retries: 60
      start_period: 10s
  redis:
    image: redis:7.2.4-bookworm
    ports: [{target: 6379, host_ip: "127.0.0.1"}]
    command: ["redis-server", "/usr/local/etc/redis/redis.conf"]
    volumes: ["./.dsfst/redis.conf:/usr/local/etc/redis/redis.conf:ro"]
    healthcheck:
      test: ["CMD-SHELL", "test \"$$(redis-cli --user test1234 -a test1234 --no-auth-warning ping)\" = PONG"]
      interval: 2s
      timeout: 5s
      retries: 60
      start_period: 5s
volumes:
  mongodb_data:
  influxdb_data:
  influxdb_config:
YAML

# Use exact commands, not argument wildcards (also works with sudo-rs).
# The APIs accept integer delay 0..500 ms and packet loss 0..50 percent.
TC="$(PATH=/usr/sbin:/sbin:$PATH command -v tc)"
INTERFACE="$(ip -o route show default | awk '{for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')"
[[ "$INTERFACE" =~ ^[a-zA-Z0-9_.-]+$ ]] || { echo 'No supported default network interface found.' >&2; exit 1; }
USER_NAME="$(id -un)"
{
    for delay in {0..500}; do
        printf '%s ALL=(root) NOPASSWD: %s qdisc replace dev %s root netem delay %sms\n' "$USER_NAME" "$TC" "$INTERFACE" "$delay"
    done
    for loss in {0..50}; do
        printf '%s ALL=(root) NOPASSWD: %s qdisc replace dev %s root netem loss %s%%\n' "$USER_NAME" "$TC" "$INTERFACE" "$loss"
    done
    printf '%s ALL=(root) NOPASSWD: %s qdisc del dev %s root\n' "$USER_NAME" "$TC" "$INTERFACE"
} > .dsfst/sudoers
sudo visudo -cf "$ROOT/.dsfst/sudoers"
sudo install -o root -g root -m 0440 .dsfst/sudoers "/etc/sudoers.d/dsfst-$(id -u)"
printf '%s\n' "$INTERFACE" > .dsfst/interface

# Download database images now, without starting any project containers.
sudo docker compose --project-name dsfst-vm --project-directory "$ROOT" \
    --env-file "$ROOT/.env" -f "$ROOT/.dsfst/compose.yaml" pull
touch .dsfst/install-complete
printf '\nInstallation complete. Start with: bash start_dsfst.sh\n'
