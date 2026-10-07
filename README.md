# D.S.F.S.T

D.S.F.S.T is an Ubuntu VM failure simulation tool. Its React dashboard reads
CPU, memory, and network measurements and manages CPU, memory, latency and
packet loss experiments. A coordinator can register other prepared VMs, read
their metrics and launch a tracked experiment batch across selected VMs.
Injections target each VM host; individual containers are not injection targets.

## Quick start

First prepare an Ubuntu 24.04 LTS x86-64 VM with AVX, internet access and a
normal user with sudo privileges. For Windows browser access, install Oracle
VirtualBox Guest Additions using [OWN_VM_SETUP.md](OWN_VM_SETUP.md).

### First installation inside Ubuntu

```bash
sudo apt update
sudo apt install -y git
git clone --branch main-based-dev-branch --single-branch https://github.com/TH-800/D.S.F.S.T.git "$HOME/D.S.F.S.T"
cd "$HOME/D.S.F.S.T"
bash setup_dsfst.sh
```

Run setup as your normal user; it requests sudo when needed. Wait for
`Full setup complete`, then open `http://localhost:3000/#/` inside Ubuntu.
This command installs the dependencies, configures the databases, enables
startup and starts the dashboard, eleven APIs and metrics collection.

### Enable Windows browser access once

Keep Ubuntu running. Download the same branch on Windows and keep the complete
project together. Open PowerShell in that project folder and run this command,
replacing the VM name, Ubuntu username and guest project path with yours:

```powershell
.\enable_vm_browser.bat -VmName 'My Ubuntu VM' -GuestUser 'myuser' -GuestProjectPath '/home/myuser/D.S.F.S.T'
```

Enter your Ubuntu password when prompted. Open the dashboard URL printed by
the helper and switch **Mock Data** to **Live API**. The API directory is
`http://<VM-IP>:3000/api`; interactive command docs are at
`http://<VM-IP>:3000/api/8009/docs` and stored metrics docs at
`http://<VM-IP>:3000/api/8008/docs`.

### Daily use

Start the prepared VM in VirtualBox and wait for the dashboard to respond.
The network and app services start automatically without a guest password
prompt. Open its saved dashboard URL from Windows. Start experiments from
the dashboard; no separate `RunALL.py` command is needed.

Inside Ubuntu, use these service controls when needed:

```bash
sudo systemctl start dsfst.service
systemctl status dsfst.service --no-pager
```

To stop the app, run `bash stop_dsfst.sh` from the installed project folder.
For manual terminal operation, stop the service first, run
`bash start_dsfst.sh`, and use Ctrl+C to stop that session.

See [DSFST_COMMANDS.txt](DSFST_COMMANDS.txt) for the complete command reference,
including smoke tests, database queries, cloning and multi-VM control.

## Multi-VM operation

Open the **VMs** page to register private VM gateway addresses, select a VM's
stored measurements, launch across one or more targets, and inspect/stop the
resulting batch. Registrations and batch references persist in MongoDB.
See [MULTI_VM_README.txt](MULTI_VM_README.txt) for endpoints and result handling.

For full Ubuntu setup in one command, run `bash setup_dsfst.sh` as your normal
user. It installs/configures the frontend, backend and databases, enables the
service and waits for startup and stored metrics to become ready.

## Set up your own VM

Follow **[Run on your own Ubuntu VM](OWN_VM_SETUP.md)** for the complete
Windows + Oracle VirtualBox setup: download this branch, install in Ubuntu,
enable automatic startup, open the dashboard and APIs from Windows, verify
live data, stop the service, and optionally clone the VM.

The tested guest is Ubuntu 24.04 LTS x86-64. The Windows batch and PowerShell
scripts are in this repository's root folder and use your local VirtualBox
installation. Supply your own VM name and Ubuntu username when running them.

## Components

- `RunALL.py` starts the frontend on port 3000 and eleven FastAPI services on
  ports 8000 through 8010.
- `experiment_orchestrator.py` creates and controls experiments, with metadata
  and logs in MongoDB and current state in Redis.
- `InjectionScripts/` runs `stress-ng` or `tc` on the VM host.
- `metrics_writer.py` samples the monitoring APIs and stores time series in
  InfluxDB. `metrics_api.py` and `reports_aggregator.py` read stored results.
- The dashboard starts in mock mode. Switch to Live API for actual measurements.
  Missing live readings are shown as unavailable rather than simulated.

## Start on Ubuntu

Use an Ubuntu x86-64 VM with AVX, a normal user with `sudo`, and internet access.
From this directory, run `bash setup_dsfst.sh` once.
Open `http://localhost:3000/#/` inside the VM. The service starts at boot.
For manual terminal operation after installation, stop the service and run
`bash start_dsfst.sh`.
The installer creates a virtual environment, downloads dependencies and
database images, and generates local credentials. The launcher starts the
databases, APIs, frontend, and metrics writer. Press Ctrl+C in its terminal to
stop the app. See [START_HERE.txt](START_HERE.txt) for setup details.

The APIs and databases bind to VM loopback. Optional Windows browser access
adds a web listener on the VM's host-only IP. Use it on a private test VM;
it has no user login. Registered VMs must already run this project.

## Prepared VirtualBox VMs on Windows

`create_dsfst_vms.bat` calls `create_dsfst_vms.ps1` to clone and start prepared
Ubuntu VMs. The PowerShell script and `VM_FACTORY_README.txt` explain how to
prepare a template from your own Ubuntu VM. For a template configured with
`enable_dsfst_autostart.sh`, run `bash stop_dsfst.sh` inside the VM to stop its
app service. The first template setup requires sudo; later clones boot without
an Ubuntu password prompt.

For direct Windows browser access, run `enable_vm_browser.bat` once. Each VM
gets a permanent IP; the dashboard and APIs share `http://<VM-IP>:3000`.
See [VM_BROWSER_README.md](VM_BROWSER_README.md) for setup, cloning, API URLs
and external collectors.

## Inspect data and call APIs

Run `.venv/bin/python dsfst_probe.py status` or
`.venv/bin/python dsfst_probe.py db` inside the Ubuntu VM. To send an explicit
API request, use `.venv/bin/python dsfst_probe.py api GET 8009 /state`.
See `DB_API_README.md` for database output, POST examples, and limits.
From Windows, `dsfst_vm_access.bat` runs those requests inside an active
VirtualBox guest and returns the JSON to Windows. See `VM_ACCESS_README.md`.
With browser access enabled, Windows can also call
`http://<VM-IP>:3000/api/8008/metrics/latest` directly over HTTP.

## Checks

`python -m compileall -q RunALL.py BaseNetworkInfo.py ExperimentMonitor.py
LinuxCpuStatus.py LinuxMemoryStatus.py experiment_orchestrator.py metrics_api.py
metrics_writer.py reports_aggregator.py vm_registry.py vm_metrics.py multi_vm.py InjectionScripts database` checks Python
syntax. From `dsft-frontend/`, run `npm ci`, `npm run check`, and
`npm run build`. Install `tests/requirements.txt` into the project virtual
environment, then run `python -m unittest discover -s tests -v`. The tests
mock system commands and database services; they do not inject failures.
On Linux, `python3 tests/linux_network_lock_smoke.py` also checks the file lock.
For the browser gateway, run `node --import tsx --test server/api-proxy.test.ts`
from `dsft-frontend/`, and `powershell -File tests/test_vm_network.ps1` from
the project root. `tests/live_vm_browser_smoke.ps1 -BaseUrl http://<VM-IP>:3000`
checks the running VM over HTTP; add `-RunExperiment` to test a bounded CPU
experiment and read its stored results.

For two prepared VMs, `tests/live_multi_vm_smoke.ps1` checks registration,
per-VM metrics/history, one-request parallel launch, reports, natural completion,
manual stop and temporary registration removal. See MULTI_VM_README.txt.
