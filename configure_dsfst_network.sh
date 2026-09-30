#!/usr/bin/env bash
# Installed once by enable_vm_browser.ps1; systemd reapplies per-VM properties at boot.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
ROOT="$PWD"
[[ "$EUID" == 0 && -f .dsfst/install-complete ]] || { echo 'Run through enable_vm_browser.bat after installing D.S.F.S.T.' >&2; exit 1; }
command -v VBoxControl >/dev/null
command -v netplan >/dev/null
get_property() { VBoxControl guestproperty get "$1" | sed -n 's/^Value: //p'; }
VM_IP="$(get_property /DSFST/HostOnlyIP)"
HOST_IP="$(get_property /DSFST/HostIP)"
MAC="$(get_property /DSFST/HostOnlyMAC)"
# The Windows helper allocates .10-.99, outside VirtualBox's default DHCP pool.
[[ "$VM_IP" =~ ^192\.168\.56\.([1-9][0-9])$ && "$HOST_IP" == 192.168.56.1 && "$MAC" =~ ^([0-9a-f]{2}:){5}[0-9a-f]{2}$ ]] || {
    echo 'Missing or invalid VirtualBox D.S.F.S.T network properties.' >&2; exit 1;
}
INTERFACE=''
for file in /sys/class/net/*/address; do
    if [[ "$(cat "$file")" == "$MAC" ]]; then INTERFACE="$(basename "$(dirname "$file")")"; break; fi
done
[[ -n "$INTERFACE" ]] || { echo "Host-only NIC $MAC was not found." >&2; exit 1; }
[[ "$ROOT" != *' '* ]] || { echo 'Use a project path without spaces.' >&2; exit 1; }

network_file=/etc/netplan/90-dsfst-hostonly.yaml
renderer=networkd
if systemctl is-active --quiet NetworkManager; then renderer=NetworkManager; fi
temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
cat > "$temporary" <<YAML
network:
  version: 2
  ethernets:
    dsfst-hostonly:
      renderer: $renderer
      match:
        macaddress: "$MAC"
      dhcp4: false
      dhcp6: false
      link-local: []
      optional: true
      addresses: [$VM_IP/24]
YAML
if ! cmp -s "$temporary" "$network_file" || ! ip -o -4 addr show dev "$INTERFACE" | grep -q " $VM_IP/24 "; then
    install -o root -g root -m 0600 "$temporary" "$network_file"
    netplan generate
    if [[ "$renderer" == NetworkManager ]]; then
        # Reload just this generated profile and activate it. Do not restart NAT.
        # NetworkManager/DBus can take a moment to answer during boot.
        for attempt in {1..30}; do
            if nmcli connection reload && nmcli --wait 5 connection up id netplan-dsfst-hostonly ifname "$INTERFACE"; then break; fi
            sleep 1
        done
    else
        netplan apply
    fi
fi
for attempt in {1..30}; do
    ip -o -4 addr show dev "$INTERFACE" | grep -q " $VM_IP/24 " && break
    sleep 1
done
ip -o -4 addr show dev "$INTERFACE" | grep -q " $VM_IP/24 " || { echo 'Host-only address did not become active.' >&2; exit 1; }
printf 'DSFST_VM_IP=%s\nDSFST_FRONTEND_MODE=production\n' "$VM_IP" > .dsfst/vm-network.env
owner="$(stat -c %U start_dsfst.sh)"
group="$(stat -c %G start_dsfst.sh)"
chown "$owner:$group" .dsfst/vm-network.env
chmod 0644 .dsfst/vm-network.env
# Ubuntu installations with UFW enabled need the single browser port allowed.
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
    ufw allow in on "$INTERFACE" from 192.168.56.0/24 to "$VM_IP" port 3000 proto tcp
fi
if [[ "${1:-}" == --install ]]; then
    cat > /etc/systemd/system/dsfst-network.service <<UNIT
[Unit]
Description=Configure this D.S.F.S.T VM's Windows access address
After=network-online.target vboxadd-service.service dsfst-clone-init.service
Wants=network-online.target
Before=dsfst.service

[Service]
Type=oneshot
ExecStart=/usr/bin/bash $ROOT/configure_dsfst_network.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
    mkdir -p /etc/systemd/system/dsfst.service.d
    cat > /etc/systemd/system/dsfst.service.d/network.conf <<UNIT
[Unit]
Requires=dsfst-network.service
After=dsfst-network.service
UNIT
    systemctl daemon-reload
    systemctl enable dsfst-network.service
    systemctl start dsfst-network.service
fi
echo "Windows dashboard: http://$VM_IP:3000/#/"
