D.S.F.S.T MULTI-VM OPERATION
===========================
Choose one running D.S.F.S.T VM as the coordinator. Open that VM's dashboard
and select the VMs navigation page. This page uses live backend services.

1. Register other prepared VMs using a name and gateway URL, for example:
       http://192.168.56.11:3000
   The coordinator stores registrations in its MongoDB. The built-in "local"
   target represents the coordinator's own VM. Registering a VM does not
   install software, create its VirtualBox machine, or share its databases.

2. Choose a VM in "VM measurements" to read that VM's stored CPU, memory and
   network readings. Offline/unavailable targets report an error; the API
   does not substitute another VM's readings.

3. Select one or more VM targets, a failure type and parameters, then launch.
   One request preflights all targets and creates a tracked batch. It creates
   a child experiment on each VM and starts those children concurrently.
   CPU/memory experiments have a duration. Latency and packet loss need a stop.

4. Inspect the batch's per-VM state and report links. Stop a batch or all active
   batches from this page. A failed launch attempts to reset every child it
   created. An unconfirmed reset remains visible as partial_failure; retry
   the stop after restoring the VM's connection. Removal is blocked while
   a registered VM belongs to a known active batch.
   Removing a registration does not delete or power off the VirtualBox VM.

ENDPOINTS
---------
Paths below are relative to the coordinator's dashboard address.

Orchestrator (8009):
    POST   /api/8009/vms
           JSON: {"name":"Clone","base_url":"http://192.168.56.11:3000"}
    GET    /api/8009/vms
    DELETE /api/8009/vms/<vm_id>

    POST   /api/8009/experiments/launch
           JSON: {"name":"two-VM CPU test","failure_type":"cpu",
                  "vm_ids":["local","REGISTERED_VM_ID"],
                  "parameters":{"cpu_percent":10,"duration_seconds":15}}
    GET    /api/8009/experiment-batches
           Optional: ?active_only=true&limit=50
    GET    /api/8009/experiment-batches/<batch_id>
    POST   /api/8009/experiment-batches/<batch_id>/stop
    POST   /api/8009/experiment-batches/emergency-stop

Metrics API (8008):
    GET /api/8008/metrics/latest?vm_id=<vm_id>
    GET /api/8008/vms/<vm_id>/metrics/latest
    GET /api/8008/vms/<vm_id>/metrics/history?measurement=cpu&minutes=15

History measurement is cpu, memory or network. Response includes vm_id,
vm_name and per-field timestamp/value series. Omitting vm_id on /metrics/latest
returns local readings, with existing CPU/memory/network fields preserved.

VM IDs come from GET /vms; the word "local" is reserved for this coordinator.
Registration accepts literal private IPv4 HTTP addresses on port 3000.
Use the assigned host-only VM IP. Redirects and environment proxies are not
used for coordinator-to-VM requests. No public internet exposure or login is
provided by this private lab application.

LAUNCH RESULTS
--------------
201 + status running: every target confirmed startup.
409/503 preflight error: no child was started because a target was busy,
unknown or unreachable.
207 + status failed: a launch failed and all possible injections were reset
or confirmed inactive. launch_errors retains the original failure.
207 + status partial_failure: a reset or child state could not be confirmed.

Batches, child IDs and start attempts are saved before injections start.
A child still marked created after a start attempt requires reset confirmation;
it is not treated as a successful rollback. Status queries
reconcile natural completion from each VM's own experiment record. If one
child completes before another, the batch stays running until all finish.
After a coordinator restart, abandoned starting and stopping operations are
reconciled
after their 180-second lease expires. Each stop has an operation ID so an old
request cannot overwrite a newer stop result. A permanently unreachable VM
cannot be proven stopped; restore its connection and retry Stop batch.

Each VM still stores its own MongoDB/InfluxDB/Redis data. The coordinator
stores VM registrations and batch references, and queries the selected VM's
Metrics API. One VM can run one local experiment at a time. Up to 16 targets
can be supplied in a batch.

ONE-COMMAND UBUNTU SETUP
-----------------------
From the full project folder, as your normal Ubuntu user:
    bash setup_dsfst.sh

This installs/configures Python services, frontend dependencies/build,
Docker database images/credentials/schema, and systemd startup, starts the
stack and waits up to twelve minutes for startup, database connections and
fresh stored metrics. Database health checks allow slower VM cold starts.
Internet and sudo access are needed during installation. Existing credentials/data are retained.
The setup refuses to interrupt a known active experiment or batch.

For a new VM's Windows browser exposure, install Guest Additions and run:
    .\enable_vm_browser.bat -VmName "My Ubuntu VM" -GuestUser "myuser"

The Windows helper also deploys the updated multi-VM backend and frontend
files when upgrading an already installed VM. Existing clone snapshots retain
their old software; prepare a fresh snapshot name before creating new clones.

LIVE VALIDATION
---------------
Backend tests:
    .venv/bin/python -m pip install -r tests/requirements.txt
    .venv/bin/python -m unittest discover -s tests -v

Windows live multi-VM test (both VMs must be available, no active experiment):
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\live_multi_vm_smoke.ps1 -CoordinatorUrl http://192.168.56.10:3000 -RemoteUrl http://192.168.56.11:3000

The live test creates bounded 10% CPU experiments on two VMs, reads per-VM
stored metrics and reports, tests stopping, and verifies removal of a temporary
registration. It leaves test experiment and batch records for inspection.
