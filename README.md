# D.S.F.S.T

D.S.F.S.T is a single Ubuntu VM failure simulation tool. Its React dashboard
reads host CPU, memory, and network measurements and manages CPU, memory,
latency, and packet loss experiments. The current target is the VM host; the
project does not yet inject faults into individual containers or remote nodes.

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
From this directory, run `bash install_dsfst.sh` once, then
`bash start_dsfst.sh`. Open `http://localhost:3000/#/` inside the VM.
The installer creates a virtual environment, downloads dependencies and
database images, and generates local credentials. The launcher starts the
databases, APIs, frontend, and metrics writer. Press Ctrl+C in its terminal to
stop the app. See `START_HERE.txt` for setup details.

The app binds its APIs and frontend to the VM loopback interface. Use it only
on a private test VM; it has no user login or remote node agent.

## Prepared VirtualBox VMs on Windows

`create_dsfst_vms.bat` calls `create_dsfst_vms.ps1` to clone and start prepared
Ubuntu VMs. The PowerShell script and `VM_FACTORY_README.txt` explain how to
prepare a template from your own Ubuntu VM. For a template configured with
`enable_dsfst_autostart.sh`, run `bash stop_dsfst.sh` inside the VM to stop its
app service. The first template setup requires sudo; later clones boot without
an Ubuntu password prompt.

## Inspect data and call APIs

Run `.venv/bin/python dsfst_probe.py status` or
`.venv/bin/python dsfst_probe.py db` inside the Ubuntu VM. To send an explicit
API request, use `.venv/bin/python dsfst_probe.py api GET 8009 /state`.
See `DB_API_README.md` for database output, POST examples, and limits.

## Checks

`python -m compileall -q RunALL.py BaseNetworkInfo.py ExperimentMonitor.py
LinuxCpuStatus.py LinuxMemoryStatus.py experiment_orchestrator.py metrics_api.py
metrics_writer.py reports_aggregator.py InjectionScripts database` checks Python
syntax. From `dsft-frontend/`, run `npm ci`, `npm run check`, and
`npm run build`. Install `tests/requirements.txt` into the project virtual
environment, then run `python -m unittest discover -s tests -v`. The tests
mock system commands and database services; they do not inject failures.
On Linux, `python3 tests/linux_network_lock_smoke.py` also checks the file lock.
