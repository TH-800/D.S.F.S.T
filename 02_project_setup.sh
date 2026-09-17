#!/usr/bin/env bash

# D.S.F.S.T - Project / Script Setup
#
# Put this file in the ROOT of the D.S.F.S.T repository and run:
#
#     chmod +x 02_project_setup.sh
#     ./02_project_setup.sh
#
# This script:
# - installs all Python packages currently required by the repo
# - installs frontend npm packages
# - starts MongoDB, InfluxDB, and Redis with Docker Compose
# - creates/copies the .env configuration
# - runs the MongoDB and InfluxDB setup scripts
#
# FIRST INFLUXDB SETUP:
# InfluxDB needs its one-time account/org/bucket setup before this script can
# create the final .env. If .env does not exist, this script opens/instructs
# you to open localhost:8086 and then asks you to paste the generated token.

set -e

# Use the directory containing this script as the project root.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=========================================="
echo " D.S.F.S.T Project Setup"
echo "=========================================="
echo "Project directory: $PROJECT_DIR"

echo
echo "[1/7] Checking repository files..."

REQUIRED_FILES=(
    "RunALL.py"
    "metrics_writer.py"
    "docker-compose.yml"
    "database/mongo_setup.py"
    "database/influx_setup.py"
    "dsft-frontend/package.json"
)

for FILE in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "$FILE" ]]; then
        echo "Missing required file: $FILE"
        echo "Place 02_project_setup.sh in the repository root."
        exit 1
    fi
done

echo "Repository files found."

echo
echo "[2/7] Installing Python packages..."

# Packages are based on the current repo imports/setup notes:
# RunALL.py: fastapi, uvicorn, psutil
# database layer: pymongo, influxdb-client, python-dotenv, redis
# metrics/orchestrator services: requests
#
# pymongo is pinned to 3.12.3 because the repo's Ubuntu 22.04 setup guide
# specifically requires that version.
python3 -m pip install \
    fastapi \
    uvicorn \
    psutil \
    requests \
    "pymongo==3.12.3" \
    influxdb-client \
    python-dotenv \
    redis

echo
echo "[3/7] Installing frontend npm packages..."

cd "$PROJECT_DIR/dsft-frontend"
npm install
cd "$PROJECT_DIR"

echo
echo "[4/7] Starting MongoDB, InfluxDB, and Redis..."

# Prefer Docker without sudo after the base setup's docker-group change.
# Fall back to sudo if the current login session has not picked up the group yet.
if docker info >/dev/null 2>&1; then
    docker compose up -d
else
    echo "Docker requires sudo in this session."
    sudo docker compose up -d
fi

echo "Waiting 10 seconds for the database containers to initialize..."
sleep 10

echo
echo "[5/7] Setting up .env..."

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo
    echo "No .env file exists yet."
    echo
    echo "InfluxDB requires ONE first-time setup:"
    echo
    echo "1. Open: http://localhost:8086"
    echo "2. Create your login."
    echo "3. Organization MUST be: dsfst-org"
    echo "4. Bucket MUST be:       dsfst-bucket"
    echo "5. Copy the generated API token."
    echo

    # Open the page automatically on desktop Linux when possible.
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open http://localhost:8086 >/dev/null 2>&1 || true
    fi

    read -r -p "Paste your InfluxDB API token here: " INFLUX_TOKEN

    if [[ -z "$INFLUX_TOKEN" ]]; then
        echo "No token was entered. Setup cannot continue."
        exit 1
    fi

    cat > "$PROJECT_DIR/.env" <<EOF
MONGO_URI=mongodb://127.0.0.1:27017/
MONGO_DB_NAME=dsfst
INFLUXDB_URL=http://127.0.0.1:8086
INFLUXDB_TOKEN=$INFLUX_TOKEN
INFLUXDB_ORG=dsfst-org
INFLUXDB_BUCKET=dsfst-bucket
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
EOF

    chmod 600 "$PROJECT_DIR/.env"
    echo ".env created."
else
    echo "Existing .env found. Keeping it."
fi

# The repo setup scripts also expect the same .env inside database/.
cp "$PROJECT_DIR/.env" "$PROJECT_DIR/database/.env"
chmod 600 "$PROJECT_DIR/database/.env"

# Make sure secrets are not accidentally committed.
touch "$PROJECT_DIR/.gitignore"

if ! grep -qxF ".env" "$PROJECT_DIR/.gitignore"; then
    echo ".env" >> "$PROJECT_DIR/.gitignore"
fi

echo
echo "[6/7] Running one-time database setup scripts..."

cd "$PROJECT_DIR/database"

python3 mongo_setup.py
python3 influx_setup.py

cd "$PROJECT_DIR"

echo
echo "[7/7] Verifying MongoDB and Redis..."

if docker info >/dev/null 2>&1; then
    docker exec dsfst-mongodb mongosh dsfst --eval "db.getCollectionNames()"
    docker exec dsfst-redis redis-cli ping
else
    sudo docker exec dsfst-mongodb mongosh dsfst --eval "db.getCollectionNames()"
    sudo docker exec dsfst-redis redis-cli ping
fi

echo
echo "=========================================="
echo " D.S.F.S.T project setup complete."
echo "=========================================="
echo
echo "Normal app startup is now:"
echo
echo "    python3 GlobalRunALL.py"
echo
echo "Dashboard:"
echo
echo "    http://localhost:3000"
echo
