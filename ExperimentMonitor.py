# ExperimentMonitor.py
# Monitors the state of all D.S.F.S.T injection processes on this machine.
# Runs as a FastAPI service on port 8000.
#
# Setup:
#   pip install fastapi uvicorn psutil
#   python -m uvicorn ExperimentMonitor:app --host 127.0.0.1 --port 8000 --reload
#
# Endpoints:
#   GET /status        -> full machine state with active experiment list
#   GET /health        -> simple alive check

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import subprocess
import psutil

app = FastAPI(title="D.S.F.S.T Experiment Monitor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Port-to-script mapping so we can resolve which service is on which port and not have any issues when reading info from em
PORT_MAP = {
    8001: "BaseNetworkInfo.py",
    8002: "LinuxCpuStatus.py",
    8003: "LinuxMemoryStatus.py",
    8004: "CPUStressInjection.py",
    8005: "NetworkLatencyInjection.py",
    8006: "PacketLossInjection.py",
    8007: "MemoryStressInjection.py",
    8008: "metrics_api.py",
    8009: "experiment_orchestrator.py",
    8010: "reports_aggregator.py",
}

# Ports that belong to injection scripts (as opposed to passive monitors)
INJECTION_PORTS = {8004, 8005, 8006, 8007}

 # Detection helpers
 
def get_listening_ports() -> dict[int, int]:
    """
    Returns a dict of {port: pid} for every TCP port in PORT_MAP that
    currently has a process listening on it.
    """
    listening = {}
    for conn in psutil.net_connections(kind="tcp"):
        if conn.status == "LISTEN" and conn.laddr.port in PORT_MAP:
            listening[conn.laddr.port] = conn.pid
    return listening


def check_stress_ng_running() -> list[dict]:
    """
    Returns a list of running stress-ng MASTER processes with their command line
    so we can tell what kind of stress is being applied.

    stress-ng always spawns one master process (which holds all the flags like
    --cpu or --vm) plus N worker child processes that have a stripped cmdline
    with no flags at all. Those workers are what were showing up as "unknown".

    The fix: skip any stress-ng process whose parent process is also stress-ng.
    That parent-check filters out every worker and leaves only the master(s).
    """
    results = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time", "ppid"]):
        try:
            if not (proc.info["name"] and "stress-ng" in proc.info["name"]):
                continue

            #  worker filter 
            # If this process's parent is also a stress-ng process it is a worker
            # spawned by the master. Skip it so we only report the master once.
            try:
                parent = psutil.Process(proc.info["ppid"])
                parent_name = parent.name()
                if "stress-ng" in parent_name:
                    continue  # this is a worker child, not the master — skip it
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # parent is gone or unreadable — treat this process as the master
                pass

            cmdline = proc.info["cmdline"] or []
            started_at = datetime.utcfromtimestamp(
                proc.info["create_time"]
            ).strftime("%Y-%m-%d %H:%M:%S")

            stress_type = "unknown"
            intensity = None

            if "--cpu" in cmdline:
                stress_type = "cpu_stress"
                idx = cmdline.index("--cpu")
                workers = cmdline[idx + 1] if idx + 1 < len(cmdline) else "?"
                intensity = f"{workers} worker(s)"

            elif "--vm" in cmdline:
                stress_type = "memory_stress"
                bytes_idx = cmdline.index("--vm-bytes") if "--vm-bytes" in cmdline else -1
                intensity = cmdline[bytes_idx + 1] if bytes_idx != -1 and bytes_idx + 1 < len(cmdline) else "?"

            results.append({
                "pid": proc.info["pid"],
                "type": stress_type,
                "intensity": intensity,
                "started_at": started_at,
            })

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return results


def check_tc_netem_active() -> list[dict]:
    """
    Checks every common network interface for active tc/netem rules.
    Returns a list of active network injection rules found.
    """
    common_interfaces = [
        "eth0", "eth1", "ens33", "ens3", "ens4",
        "enp0s3", "enp0s8", "wlan0", "lo",
    ]

    # also scan whatever interfaces psutil can see on this machine
    try:
        live_interfaces = list(psutil.net_if_stats().keys())
        for iface in live_interfaces:
            if iface not in common_interfaces:
                common_interfaces.append(iface)
    except Exception:
        pass

    active_rules = []
    for iface in common_interfaces:
        try:
            result = subprocess.run(
                ["tc", "qdisc", "show", "dev", iface],
                capture_output=True,
                text=True,
                timeout=3,
            )
            output = result.stdout.strip()

            # a bare "noqueue" or "pfifo_fast" means nothing is injected
            if "netem" in output:
                rule = {
                    "interface": iface,
                    "rule": output,
                    "type": None,
                    "params": {},
                }

                if "delay" in output:
                    rule["type"] = "network_latency"
                    # extract the delay value e.g. "delay 200ms"
                    parts = output.split()
                    try:
                        idx = parts.index("delay")
                        rule["params"]["delay"] = parts[idx + 1]
                    except (ValueError, IndexError):
                        pass

                if "loss" in output:
                    rule["type"] = "packet_loss" if rule["type"] is None else rule["type"] + "+packet_loss"
                    parts = output.split()
                    try:
                        idx = parts.index("loss")
                        rule["params"]["loss_percent"] = parts[idx + 1]
                    except (ValueError, IndexError):
                        pass

                active_rules.append(rule)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # tc is not installed or timed out skip it silently because why not
            pass
        except Exception:
            pass

    return active_rules


def build_active_experiments(stress_procs: list, tc_rules: list, listening_ports: dict) -> list[dict]:
    """
    Combines all detection sources into a unified list of active experiments.
    """
    experiments = []

    for proc in stress_procs:
        experiments.append({
            "experiment_id": f"stress-{proc['pid']}",
            "type": proc["type"],
            "source": "stress-ng process",
            "pid": proc["pid"],
            "intensity": proc["intensity"],
            "started_at": proc["started_at"],
            "state": "running",
        })

    for rule in tc_rules:
        experiments.append({
            "experiment_id": f"netem-{rule['interface']}",
            "type": rule["type"] or "network_injection",
            "source": f"tc/netem on {rule['interface']}",
            "interface": rule["interface"],
            "params": rule["params"],
            "state": "running",
        })

    return experiments


def check_uvicorn_shutting_down(pid: int) -> bool:
    """
    Heuristic: a uvicorn process that exists but has no child workers
    is likely in the process of shutting down.
    """
    try:
        proc = psutil.Process(pid)
        children = proc.children(recursive=False)
        # if the process is still alive but has no children it may be winding down
        return len(children) == 0 and proc.status() == psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


 # State machine logic
 
def determine_state(active_experiments: list, listening_ports: dict) -> str:
    """
    Maps the observed system state to one of:
      idle      - no injections running, injection services may or may not be up
      running   - at least one active injection (stress-ng or tc/netem)
      stopping  - injection services detected shutting down
      complete  - injection services were up but no active injections found
                  (means an experiment ran and finished or was reset)
    """
    injection_services_up = any(p in listening_ports for p in INJECTION_PORTS)
    has_active_injections = len(active_experiments) > 0

    # check if any injection port process looks like it is shutting down
    stopping = any(
        check_uvicorn_shutting_down(pid)
        for port, pid in listening_ports.items()
        if port in INJECTION_PORTS
    )

    if stopping:
        return "stopping"
    if has_active_injections:
        return "running"
    if injection_services_up:
        # services are alive but nothing is injecting — last run completed
        return "complete"
    return "idle"


 # API endpoints
 
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ExperimentMonitor",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/status")
def get_status():
    """
    Returns the full machine state.

    Response schema:
    {
      "state": "idle" | "running" | "stopping" | "complete",
      "timestamp": "...",
      "services": {
        "8001": {"script": "...", "online": true/false},
        ...
      },
      "active_experiments": [   # only present when state == "running"
        { "experiment_id": "...", "type": "...", ... }
      ],
      "stopping_experiments": [ # only present when state == "stopping"
        { ... }
      ],
      "summary": {
        "total_active": int,
        "services_online": int,
        "injection_services_online": int,
      }
    }
    """
    listening_ports = get_listening_ports()
    stress_procs    = check_stress_ng_running()
    tc_rules        = check_tc_netem_active()
    active_exps     = build_active_experiments(stress_procs, tc_rules, listening_ports)
    state           = determine_state(active_exps, listening_ports)

    # build perservice status map
    services = {}
    for port, script in PORT_MAP.items():
        online = port in listening_ports
        entry = {
            "script": script,
            "port": port,
            "online": online,
            "is_injection_service": port in INJECTION_PORTS,
        }
        if online:
            entry["pid"] = listening_ports[port]
        services[str(port)] = entry

    response = {
        "state": state,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "services": services,
        "summary": {
            "total_active_experiments": len(active_exps),
            "services_online": sum(1 for s in services.values() if s["online"]),
            "injection_services_online": sum(
                1 for p, s in services.items()
                if s["online"] and s["is_injection_service"]
            ),
        },
    }

    if state == "running":
        response["active_experiments"] = active_exps

    elif state == "stopping":
        # report which injection services appear to be winding down and which are done 
        stopping = [
            {
                "script": PORT_MAP[port],
                "port": port,
                "pid": listening_ports[port],
            }
            for port in INJECTION_PORTS
            if port in listening_ports and check_uvicorn_shutting_down(listening_ports[port])
        ]
        response["stopping_experiments"] = stopping

    elif state == "complete":
        response["message"] = (
            "Injection services are online but no active injections detected. "
            "The previous experiment has completed or was reset."
        )

    elif state == "idle":
        response["message"] = "No injection services running. System is idle."

    return response


@app.get("/services")
def get_services():
    """
    Quick check of which D.S.F.S.T services are currently listening.
    """
    listening_ports = get_listening_ports()
    return {
        str(port): {
            "script": script,
            "online": port in listening_ports,
            "pid": listening_ports.get(port),
        }
        for port, script in PORT_MAP.items()
    }