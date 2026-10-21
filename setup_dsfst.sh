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
    python3 dsfst_readiness.py --check-idle
    sudo systemctl stop dsfst.service
fi
bash install_dsfst.sh
bash enable_dsfst_autostart.sh
if command -v VBoxControl >/dev/null && VBoxControl guestproperty get /DSFST/HostOnlyIP 2>/dev/null | grep -q '^Value: 192\.168\.56\.'; then
    sudo bash configure_dsfst_network.sh --install
fi
sudo systemctl restart dsfst.service
# The launcher allows 240s for databases and 420s for API/frontend startup.
python3 dsfst_readiness.py --timeout 720
echo 'Full setup complete: databases, APIs, dashboard and metrics writer are ready.'
cat .dsfst/addresses.txt
