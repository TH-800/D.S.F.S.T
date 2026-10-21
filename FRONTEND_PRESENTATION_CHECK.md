# Frontend presentation check — 22 October 2026

AI-assisted integration review on 21 October. Combines Momin's SCRUM-12/16/18/20/21 work with Tarun's development branch through 9e15009.

## What changed

Resolved overlapping service indicators by preserving both the reusable service lights and the independent monitor health check. Kept Tarun's request cancellation, VM identity validation, active-batch visibility and process-group reset confirmation. Preserved the local memory allocation guard and child reaping. Combined both frontend test suites and retained explicit target selection, the first-use guide and confirmed notifications.

Live Logs now show only persisted database records; a database failure is visible rather than silently mixing in simulated session entries.

## Windows demonstration

Windows can open the dashboard served by the Linux VM. This is the same frontend as Linux; no separate Windows InfluxDB or MongoDB is required for this path. Use the VM's actual host-only address, for example http://192.168.56.10:3000/#/ (example only), or forward the VM's port 3000 to an unused Windows port. Opening localhost:3000 on Windows without forwarding instead reaches a Windows server, whose API proxy expects Python services on Windows loopback.

The main Dashboard reads live monitoring endpoints for its current host. The VMs page's measurement selector reads stored InfluxDB metrics for the chosen registered VM via /api/8008/vms/{id}/metrics/latest. Logs, presets and Reports use the current host's backend; this is not a global combined database browser. Remote batch members have per-VM report links.

Before presenting:
1. Update and rebuild the same integrated revision on the VM that serves the page; restart that server and keep metrics_writer.py running.
2. From Windows, open the actual VM URL and select Live API.
3. Show CPU, memory, network, monitor health and service lights.
4. On VMs, select each available VM and verify the stored measurement timestamps advance. Missing samples must not be presented as fresh data.
5. Use a bounded CPU experiment agreed with Tarun. Check start confirmation, metric changes, stop confirmation and the saved report. Reopen a saved preset to demonstrate persistence.
6. Show the guide briefly. Keep screenshots as backup, clearly identified as earlier captures.

## Validation and limits

TypeScript checks, both existing frontend suites, the PPP suite, gateway tests, and the production build passed locally. New Logs regression checks cover mock/live isolation, connection failure and recovery. No real VM experiment was launched here.

Python: 79 tests in the filtered suite, 74 passed and 5 setup tests skipped because this environment runs as root. One additional real process-group test failed in this execution environment and was excluded from the rerun; it still needs verification on Ubuntu. Python tests used FastAPI 0.115.12. Installing the newest unpinned FastAPI caused the pre-existing Query(enum=...) usage to fail at import; dependency pinning remains a team follow-up.

This does not verify Momin's current Windows networking, real VM databases, two-live-VM operation, or a complete live experiment/report rehearsal. Existing dependency audit findings are not resolved by this integration.

## Short speaking script

“My part is the frontend. I worked on the VM controls, saved experiment settings, service connection lights, the first-use guide and start/stop messages, with AI assistance.

From Windows, I can open the dashboard connected to our Linux VM. The dashboard shows its live CPU, memory and network readings. Green service lights mean those services are reachable; they do not mean an experiment is running.

On the VMs page, I can choose which registered machine's stored readings to view and select machines for an experiment. The readings come through the backend APIs, while the databases stay on Linux. I also added messages to show whether a start or stop was confirmed.

Tarun will demonstrate the Linux side while I show how the frontend displays the results.”

Only claim a Windows/live demonstration succeeded after the rehearsal above actually succeeds.
