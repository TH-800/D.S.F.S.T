# Open each VM from Windows

For a fresh installation on another computer, follow
[OWN_VM_SETUP.md](OWN_VM_SETUP.md) first. It explains how to download this
branch, install Guest Additions and the app, and enable startup in your own VM.

Each prepared VM gets a permanent VirtualBox host-only IP: `192.168.56.10`,
`192.168.56.11`, and so on. Windows uses `192.168.56.1`. Adapter 1 keeps NAT
internet access; adapter 2 connects Windows to the VMs. This network is local
to this computer and its VMs.

## Set up an existing Ubuntu VM once

Install VirtualBox Guest Additions in Ubuntu. Copy this whole updated project
into the VM, then run `bash setup_dsfst.sh` as your normal Ubuntu user.
For an already installed VM, the Windows helper copies the required browser
files, checks their types, and rebuilds the dashboard automatically.

From Windows Command Prompt in this project folder:

```bat
enable_vm_browser.bat -VmName "My Ubuntu VM" -GuestUser myuser
```

For this computer's prepared VM, just run `enable_vm_browser.bat`.
It asks once for the Ubuntu password, gracefully reboots the VM to attach
adapter 2, installs its network boot service, and prints the permanent URL.
It refuses to restart an active experiment. Optional arguments:

- `-GuestProjectPath "/home/myuser/path/to/project"` overrides service path detection.
- `-Address 192.168.56.20` selects an unused address from `.10` through `.99`.
- `-PasswordFile` supplies a protected password file for automation.

The account needs sudo access for this one-time setup. Passwords are not saved
in the project. Restarting an already prepared VM needs no password.

## Browser and API addresses

Replace the example IP with the address printed for your VM. On the dashboard,
switch **Mock Data** to **Live API** for actual VM readings.

| Purpose | Address |
| --- | --- |
| Dashboard | `http://192.168.56.10:3000/#/` |
| API directory | `http://192.168.56.10:3000/api` |
| Live CPU | `http://192.168.56.10:3000/api/8002/cpu` |
| Live memory | `http://192.168.56.10:3000/api/8003/memory` |
| Live network | `http://192.168.56.10:3000/api/8001/network` |
| Stored InfluxDB metrics | `http://192.168.56.10:3000/api/8008/metrics/latest` |
| Experiment records | `http://192.168.56.10:3000/api/8008/experiments?limit=10` |
| Recent logs | `http://192.168.56.10:3000/api/8008/logs/recent?limit=20` |
| Experiment state | `http://192.168.56.10:3000/api/8009/state` |
| Metrics API documentation | `http://192.168.56.10:3000/api/8008/docs` |
| Experiment control documentation | `http://192.168.56.10:3000/api/8009/docs` |

All Python services on ports 8000-8010 are available under `/api/<port>`.
Their `/docs` pages let you send GET and POST requests. The web server forwards
these paths to that VM's loopback services. Only the web server's TCP port 3000
listens on the assigned host-only IP. The gateway rejects unknown host headers
and requests originating from a different website. Every peer on this private
VirtualBox network can use the app; the project has no user login.

## Collect data for an external database

A collector on Windows can read JSON without guest commands or a password:

```powershell
$base = 'http://192.168.56.10:3000'
$metrics = Invoke-RestMethod "$base/api/8008/metrics/latest"
$metrics | ConvertTo-Json -Depth 8
$experiments = Invoke-RestMethod "$base/api/8008/experiments?limit=10"
```

Poll the metrics endpoint and insert its values and timestamps into your
database. Tag collected rows with the VM name or source IP so measurements
from different VMs remain distinguishable. For one experiment, read `/api/8008/experiments/<id>/metrics`,
`/api/8008/experiments/<id>/logs`, `/api/8008/experiments/<id>/report`, or
`/api/8008/experiments/<id>/export`. See `/api/8008/docs` for filters and formats.
Raw database probes still work through `dsfst_vm_access.bat`; the database
ports themselves remain inside Ubuntu.

To create an experiment from PowerShell (starting it is a separate POST):

```powershell
$body = @{name='Windows API test'; failure_type='cpu'; target_container='host'; parameters=@{cpu_percent=10; duration_seconds=10}} | ConvertTo-Json
$experiment = Invoke-RestMethod "$base/api/8009/experiments" -Method Post -ContentType 'application/json' -Body $body
```

## Create multiple VMs

Prepare an updated template snapshot once, then clone it:

```bat
enable_vm_browser.bat -VmName "My Ubuntu VM" -GuestUser myuser -PrepareTemplate
create_dsfst_vms.bat 2 -TemplateVm "My Ubuntu VM"
```

The default snapshot is `dsfst-browser-ready`. Each clone gets a fresh MAC and
unused IP. Its boot service reads its own VirtualBox properties and configures
the address before starting the app. The saved network configuration matches
the template's MAC, so a new clone does not activate the template's old static
address. Clone initialization creates separate database volumes and credentials.

Windows lists all assignments in `vm-addresses.json`; Ubuntu lists its URLs in
`.dsfst/addresses.txt`. Keep the project at its installed guest path. Preparing
a new snapshot is necessary after updating an older template. If that snapshot
name already exists, use `-SnapshotName your-new-name` in both commands.

For troubleshooting, run `systemctl status dsfst-network.service dsfst.service`
and `journalctl -u dsfst-network.service -u dsfst.service --no-pager` in Ubuntu.
The helper requires a free second adapter or one already on this host-only
network. It avoids the default DHCP pool and checks other registered VM IPs.
If UFW is active, setup allows TCP 3000 only on the host-only adapter.
