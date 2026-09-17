#!/usr/bin/env bash

# D.S.F.S.T - Project / Script Setup
#
# Put this file INSIDE the project root, beside:
#   RunALL.py
#   metrics_writer.py
#   docker-compose.yml
#   database/
#   dsft-frontend/
#
# Then run:
#
#   chmod +x 02_project_setup.sh
#   ./02_project_setup.sh
#
# This script creates a project-local Python virtual environment (.venv).
# This avoids Ubuntu's "externally-managed-environment" pip restriction.
#
# The virtual environment is also important because GlobalRunALL.py uses
# sys.executable, so if GlobalRunALL.py is started with .venv/bin/python,
# RunALL.py and metrics_writer.py will use the same installed packages.

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

VENV_DIR="$PROJECT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

echo "=========================================="
echo " D.S.F.S.T Project Setup"
echo "=========================================="
echo "Project directory: $PROJECT_DIR"

echo
echo "[1/8] Checking repository files..."

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
        echo "Put this script inside the project root."
        exit 1
    fi
done

echo "Repository files found."

echo
echo "[2/8] Creating Python virtual environment..."

if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
    echo "Created: $VENV_DIR"
else
    echo "Existing virtual environment found."
fi

echo
echo "[3/8] Installing Python packages into .venv..."

"$VENV_PY" -m pip install --upgrade pip setuptools wheel

# Use a current PyMongo release rather than the old 3.12.3 pin.
# The machine shown in the debug log runs Python 3.14, and current PyMongo
# provides Python 3.14 builds while the old 3.12.3 release predates Python 3.14.
"$VENV_PIP" install \
    fastapi \
    uvicorn \
    psutil \
    requests \
    pymongo \
    influxdb-client \
    python-dotenv \
    redis

echo
echo "[4/8] Installing frontend npm packages..."

cd "$PROJECT_DIR/dsft-frontend"
npm install
cd "$PROJECT_DIR"

echo
echo "[5/8] Starting MongoDB, InfluxDB, and Redis..."

if docker info >/dev/null 2>&1; then
    docker compose up -d
else
    echo "Docker still requires sudo in this login session."
    sudo docker compose up -d
fi

echo "Waiting 10 seconds for database containers..."
sleep 10

echo
echo "[6/8] Configuring .env..."

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo
    echo "No .env file exists yet."
    echo
    echo "Complete the one-time InfluxDB setup:"
    echo
    echo "  URL:          http://localhost:8086"
    echo "  Organization: dsfst-org"
    echo "  Bucket:       dsfst-bucket"
    echo
    echo "Then copy the generated API token."
    echo

    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open http://localhost:8086 >/dev/null 2>&1 || true
    fi

    read -r -p "Paste your InfluxDB API token here: " INFLUX_TOKEN

    if [[ -z "$INFLUX_TOKEN" ]]; then
        echo "No token entered. Stopping setup."
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

cp "$PROJECT_DIR/.env" "$PROJECT_DIR/database/.env"
chmod 600 "$PROJECT_DIR/database/.env"

touch "$PROJECT_DIR/.gitignore"

if ! grep -qxF ".env" "$PROJECT_DIR/.gitignore"; then
    echo ".env" >> "$PROJECT_DIR/.gitignore"
fi

if ! grep -qxF ".venv/" "$PROJECT_DIR/.gitignore"; then
    echo ".venv/" >> "$PROJECT_DIR/.gitignore"
fi

echo
echo "[7/8] Running database setup scripts with the virtual environment..."

cd "$PROJECT_DIR/database"

"$VENV_PY" mongo_setup.py
"$VENV_PY" influx_setup.py

cd "$PROJECT_DIR"

echo
echo "[8/8] Checking Docker containers..."

if docker info >/dev/null 2>&1; then
    docker compose ps
else
    sudo docker compose ps
fi

echo
echo "=========================================="
echo " D.S.F.S.T project setup complete."
echo "=========================================="
echo
echo "IMPORTANT:"
echo "The project's Python packages are installed inside:"
echo
echo "    $VENV_DIR"
echo
echo "Start the app using the virtual environment:"
echo
echo "    .venv/bin/python GlobalRunALL.py"
echo
echo "Or activate it first:"
echo
echo "    source .venv/bin/activate"
echo "    python GlobalRunALL.py"
echo
echo "Dashboard:"
echo
echo "    http://localhost:3000"
echo
