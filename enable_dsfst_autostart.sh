#!/usr/bin/env bash
# Run once inside the prepared template VM, as its normal Ubuntu user.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
ROOT="$PWD"
[[ "$EUID" != 0 && -f .dsfst/install-complete && -f start_dsfst.sh && -f dsfst_clone_init.sh ]] || {
    echo 'Run this as the normal user after bash install_dsfst.sh.' >&2
    exit 1
}
[[ "$ROOT" != *' '* ]] || { echo 'Move the project to a path without spaces first.' >&2; exit 1; }
getent group docker >/dev/null || { echo 'Docker is not installed.' >&2; exit 1; }

cat > .dsfst/dsfst.service <<UNIT
[Unit]
Description=D.S.F.S.T dashboard, APIs, and metrics writer
Requires=docker.service dsfst-clone-init.service
After=network-online.target docker.service dsfst-clone-init.service
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
SupplementaryGroups=docker
WorkingDirectory=$ROOT
Environment=DSFST_UNATTENDED=1
ExecStartPre=+/usr/sbin/modprobe sch_netem
ExecStart=/usr/bin/bash $ROOT/start_dsfst.sh
Restart=on-failure
RestartSec=15
TimeoutStopSec=45
KillMode=mixed

[Install]
WantedBy=multi-user.target
UNIT
cat > .dsfst/dsfst-clone-init.service <<UNIT
[Unit]
Description=Give a D.S.F.S.T clone fresh database volumes and app secrets
Requires=docker.service
After=docker.service
Before=dsfst.service

[Service]
Type=oneshot
ExecStart=/usr/bin/bash $ROOT/dsfst_clone_init.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
sudo install -o root -g root -m 0644 /dev/stdin /etc/dsfst-template-uuid <<< "$(sudo cat /sys/class/dmi/id/product_uuid)"
sudo install -o root -g root -m 0644 .dsfst/dsfst-clone-init.service /etc/systemd/system/dsfst-clone-init.service
sudo install -o root -g root -m 0644 .dsfst/dsfst.service /etc/systemd/system/dsfst.service
sudo systemctl daemon-reload
sudo systemctl enable dsfst-clone-init.service
sudo systemctl enable dsfst.service
echo 'Autostart installed. To run it now: sudo systemctl start dsfst.service'
