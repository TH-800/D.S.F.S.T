#!/usr/bin/env bash

# D.S.F.S.T - Base Ubuntu/Debian Linux Setup
# Run this ONCE on a fresh Ubuntu/Debian machine.
#
# Installs:
# - Docker Engine + Docker Compose plugin
# - Python 3 + pip + venv support
# - stress-ng for CPU/memory failure injection
# - Linux networking/ping tools
# - Git
# - Node.js 22 + npm
# - util-linux-extra so the "newgrp" command is available on newer Ubuntu
#
# After this script finishes, either:
#   1. log out and back in, OR
#   2. run: newgrp docker
#
# Then run 02_project_setup.sh from inside the project folder.

set -e

echo "=========================================="
echo " D.S.F.S.T Base Linux Setup"
echo "=========================================="

. /etc/os-release

if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
    echo "This script is intended for Ubuntu or Debian."
    echo "Detected: $ID"
    exit 1
fi

echo
echo "[1/7] Removing conflicting/old Docker packages if present..."

sudo apt remove -y \
    docker.io \
    docker-compose \
    docker-compose-v2 \
    docker-doc \
    docker-buildx \
    podman-docker \
    containerd \
    runc 2>/dev/null || true

echo
echo "[2/7] Installing base Linux packages..."

sudo apt update

sudo apt install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    python3 \
    python3-pip \
    python3-venv \
    stress-ng \
    iproute2 \
    iputils-ping \
    util-linux-extra

echo
echo "[3/7] Adding Docker's official repository..."

sudo install -m 0755 -d /etc/apt/keyrings

sudo curl -fsSL "https://download.docker.com/linux/$ID/gpg" \
    -o /etc/apt/keyrings/docker.asc

sudo chmod a+r /etc/apt/keyrings/docker.asc

if [[ "$ID" == "ubuntu" ]]; then
    DOCKER_SUITE="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
else
    DOCKER_SUITE="$VERSION_CODENAME"
fi

sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/$ID
Suites: $DOCKER_SUITE
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update

echo
echo "[4/7] Installing Docker Engine and Docker Compose..."

sudo apt install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

sudo systemctl enable --now docker

# Allows this user to run Docker without sudo after a new login/newgrp.
sudo usermod -aG docker "$USER"

echo
echo "[5/7] Installing Node.js 22 and npm..."

curl -fsSL https://deb.nodesource.com/setup_22.x -o /tmp/nodesource_setup.sh
sudo bash /tmp/nodesource_setup.sh
sudo apt install -y nodejs
rm -f /tmp/nodesource_setup.sh

echo
echo "[6/7] Applying the repo's VMware/VirtualBox Docker networking fix when needed..."

VIRT="$(systemd-detect-virt 2>/dev/null || true)"

if [[ "$VIRT" == "vmware" || "$VIRT" == "oracle" ]]; then
    echo "Virtual machine detected: $VIRT"

    sudo tee /etc/systemd/system/docker-iptables-fix.service > /dev/null <<'EOF'
[Unit]
Description=Fix Docker iptables after VM boot
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/bin/systemctl restart docker
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable docker-iptables-fix.service

    echo "Docker VM networking fix installed."
else
    echo "VMware/VirtualBox not detected. Skipping VM-only networking fix."
fi

echo
echo "[7/7] Installed versions:"
echo

python3 --version
pip3 --version
node --version
npm --version
sudo docker --version
sudo docker compose version

echo
echo "=========================================="
echo " Base Linux setup complete."
echo "=========================================="
echo
echo "Docker group access was added for user: $USER"
echo
echo "Either log out and back in once, or run:"
echo
echo "    newgrp docker"
echo
echo "Then run 02_project_setup.sh from the project root."
