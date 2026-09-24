#!/usr/bin/env bash
# Stop the D.S.F.S.T systemd service installed by enable_dsfst_autostart.sh.
set -euo pipefail

sudo systemctl stop dsfst.service
echo 'D.S.F.S.T service stopped. Its database containers and data remain available.'
