# RunAll.py
# Starts every D.S.F.S.T service (FastAPI backends + React frontend) in one command.
# Run this from the root of the D.S.F.S.T-dev directory:
#
#   python RunAll.py
#
# Press Ctrl+C to shut it all down
#
# Requirements:
#   pip install fastapi uvicorn psutil
#   npm (for the React frontend)

import subprocess
import sys
import os
import time
import signal
import threading

# Configuration edit these paths if you move scripts  DO EDIT THE PATHS
# OR KEEP THE SAME FOLDER AND STUFF THE SAME 

# absolute path to the D.S.F.S.T-dev directory
# defaults to the folder this script lives in
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# path to the React frontend folder
FRONTEND_DIR = os.path.join(BASE_DIR, "dsft-frontend")

# path to the InjectionScripts subfolder
INJECTION_DIR = os.path.join(BASE_DIR, "InjectionScripts")

# uvicorn executable — uses the system one; swap for a venv path if needed
# e.g. os.path.join(BASE_DIR, "venv", "bin", "uvicorn")
UVICORN = "uvicorn"

# how long to wait (seconds) between starting each service
# gives each one time to bind its port before the next one starts
STARTUP_DELAY = 1.5

# Service definitions
# { "name": display name, "module": uvicorn app string, "port": int,
#   "cwd": working directory for the process }


# -----------------------------------------------------------------------


#service table to be used in a loop to launch all the scripts 
#dont change any of the ports and dont change anything here or else it breaks 
SERVICES = [
    #  monitor (starts first so it's ready when everything else comes up) 
    {
        "name": "ExperimentMonitor",
        "module": "ExperimentMonitor:app",
        "port": 8000,
        "cwd": BASE_DIR,
    },
    # passive monitoring scripts 
    {
        "name": "BaseNetworkInfo",
        "module": "BaseNetworkInfo:app",
        "port": 8001,
        "cwd": BASE_DIR,
    },
    {
        "name": "LinuxCpuStatus",
        "module": "LinuxCpuStatus:app",
        "port": 8002,
        "cwd": BASE_DIR,
    },
    {
        "name": "LinuxMemoryStatus",
        "module": "LinuxMemoryStatus:app",
        "port": 8003,
        "cwd": BASE_DIR,
    },
    # injection scripts 
    {
        "name": "CPUStressInjection",
        "module": "CPUStressInjection:app",
        "port": 8004,
        "cwd": INJECTION_DIR,
    },
    {
        "name": "NetworkLatencyInjection",
        "module": "NetworkLatencyInjection:app",
        "port": 8005,
        "cwd": INJECTION_DIR,
    },
    {
        "name": "PacketLossInjection",
        "module": "PacketLossInjection:app",
        "port": 8006,
        "cwd": INJECTION_DIR,
    },
    {
        "name": "MemoryStressInjection",
        "module": "MemoryStressInjection:app",
        "port": 8007,
        "cwd": INJECTION_DIR,
    },
    # persistence + orchestration layer i hate IPV6 AND LINUX VMWARE BREAKING THE IP ROUTING TABLES
    # SUDO NANO AND FOLLOW THE TXT FILE FOR THE IP TABLE FIXING 
    
    {
        "name": "MetricsAPI",
        "module": "metrics_api:app",
        "port": 8008,
        "cwd": BASE_DIR,
    },
    {
        "name": "ExperimentOrchestrator",
        "module": "experiment_orchestrator:app",
        "port": 8009,
        "cwd": BASE_DIR,
    },
    {
        "name": "ReportsAggregator",
        "module": "reports_aggregator:app",
        "port": 8010,
        "cwd": BASE_DIR,
    },

]

# Colour helpers for terminal output becuase my eyes hurt looking at things  note this was vibe coded

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"

def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def err(msg):  print(f"  {RED}✖{RESET}  {msg}")
def info(msg): print(f"  {CYAN}→{RESET}  {msg}")



# Port availability check

def port_in_use(port: int) -> bool:
    #returns True if something is already listening on the given port
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    #Blocks this until a port is accepting connections or the timeout is reached
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_in_use(port):
            return True
        time.sleep(0.3)
    return False


# Process tracking

# list of (name, subprocess.Popen) tuples so we can kill them all on exit
running_processes: list[tuple[str, subprocess.Popen]] = []

def stream_output(name: str, proc: subprocess.Popen):
    
    ##Reads stdout/stderr from a subprocess in a background thread and
    ##prefixes each line with the service name so mixed output is readable.
    
    prefix = f"{DIM}[{name}]{RESET} "
    try:
        for line in proc.stdout:
            text = line.decode(errors="replace").rstrip()
            if text:
                print(f"{prefix}{text}")
    except Exception:
        pass

# Startup

def start_fastapi_service(service: dict) -> subprocess.Popen | None:
    """
    Launches a single uvicorn service. Returns the Popen object or None on failure.
    """
    port = service["port"]
    name = service["name"]

    if port_in_use(port):
        warn(f"{name}: port {port} is already in use — skipping")
        return None

    cmd = [
        UVICORN,
        service["module"],
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning",   # suppress info spam errors still show
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=service["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # merge stderr into stdout
        )

        # stream output in a background thread
        t = threading.Thread(target=stream_output, args=(name, proc), daemon=True)
        t.start()

        # wait up to 8 s for the port to come up
        if wait_for_port(port, timeout=8.0):
            ok(f"{BOLD}{name}{RESET}{GREEN} — listening on http://127.0.0.1:{port}{RESET}")
            return proc
        else:
            err(f"{name} — did not bind to port {port} in time")
            proc.terminate()
            return None

    except FileNotFoundError:
        err(f"{name} — '{UVICORN}' not found. Is it installed? (pip install uvicorn)")
        return None
    except Exception as e:
        err(f"{name} — failed to start: {e}")
        return None


def start_frontend() -> subprocess.Popen | None:
    
    #Runs `npm run dev` inside the frontend directory.
    
    if not os.path.isdir(FRONTEND_DIR):
        err(f"Frontend directory not found: {FRONTEND_DIR}")
        return None

    if port_in_use(3000):
        warn("Frontend: port 3000 is already in use — skipping npm run dev")
        return None

    # make sure node_modules exists
    if not os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules")):
        print()
        info("node_modules not found — running npm install first (this may take a minute)...")
        try:
            subprocess.run(
                ["npm", "install"],
                cwd=FRONTEND_DIR,
                check=True,
            )
        except subprocess.CalledProcessError:
            err("npm install failed — frontend will not start")
            return None

    try:
        proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=FRONTEND_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        t = threading.Thread(
            target=stream_output, args=("Frontend", proc), daemon=True
        )
        t.start()

        # Vite can take a few seconds to compile #vite is also the frontend display i think 
        if wait_for_port(3000, timeout=30.0):
            ok(f"{BOLD}Frontend{RESET}{GREEN} — http://localhost:3000/#/{RESET}")
            return proc
        else:
            # Vite sometimes binds on a different port — warn but keep the process
            warn("Frontend: port 3000 didn't respond in 30 s — Vite may have chosen another port")
            return proc

    except FileNotFoundError:
        err("npm not found — install Node.js to run the frontend")
        return None
    except Exception as e:
        err(f"Frontend — failed to start: {e}")
        return None

# Shutdown

def shutdown_all():
    """Terminate every process we started  forcefully"""
    print()
    print(f"{YELLOW}Shutting down all services…{RESET}")
    for name, proc in running_processes:
        if proc.poll() is None:  # still alive then
            info(f"Stopping {name}…")
            proc.terminate()

    # give them 5 seconds to exit 
    deadline = time.time() + 5.0
    for name, proc in running_processes:
        remaining = max(0, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            warn(f"{name} did not exit in time — sending SIGKILL")
            proc.kill()

    ok("All services stopped.")


def handle_signal(signum, frame):
    shutdown_all()
    sys.exit(0)


# Mainly i used vibe coding here to make it easy for me to debug it inthe terminal 
# by having color coding for the services 


def print_banner():
    print()
    print(f"{BOLD}{CYAN}  D.S.F.S.T — Service Launcher{RESET}")
    print(f"  {DIM}Distributed Systems Failure Simulation Tool{RESET}")
    print()


def print_summary():
    print()
    print(f"{BOLD}  Service URLs{RESET}")
    print(f"  {DIM}{'─' * 50}{RESET}")
    print(f"  {GREEN}Frontend{RESET}              http://localhost:3000/#/")
    print(f"  {GREEN}ExperimentMonitor{RESET}     http://127.0.0.1:8000/status")
    print(f"  {GREEN}BaseNetworkInfo{RESET}        http://127.0.0.1:8001/network")
    print(f"  {GREEN}LinuxCpuStatus{RESET}         http://127.0.0.1:8002/cpu")
    print(f"  {GREEN}LinuxMemoryStatus{RESET}      http://127.0.0.1:8003/memory")
    print(f"  {GREEN}CPUStressInjection{RESET}     http://127.0.0.1:8004/inject/cpu")
    print(f"  {GREEN}NetworkLatencyInj.{RESET}     http://127.0.0.1:8005/inject/latency/{{ms}}")
    print(f"  {GREEN}PacketLossInjection{RESET}    http://127.0.0.1:8006/inject/packetloss/{{%}}")
    print(f"  {GREEN}MemoryStressInj.{RESET}       http://127.0.0.1:8007/inject/memory")
    print(f"  {GREEN}MetricsAPI{RESET}             http://127.0.0.1:8008/experiments")
    print(f"  {GREEN}ExperimentOrchest.{RESET}     http://127.0.0.1:8009/state")
    print(f"  {GREEN}ReportsAggregator{RESET}      http://127.0.0.1:8010/reports/aggregate")
    print()
    print(f"  {DIM}Run  python metrics_writer.py  in a separate terminal to persist metrics.{RESET}")
    print(f"  {DIM}Press Ctrl+C to stop all services.{RESET}")
    print()
#end of vibe code snippet

def main():
    print_banner()

    # register signal handlers for Ctrl+C and kill
    signal.signal(signal.SIGINT,  handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    #  start FastAPI services 
    print(f"{BOLD}  Starting backend services…{RESET}")
    print()

    for service in SERVICES:
        proc = start_fastapi_service(service)
        if proc:
            running_processes.append((service["name"], proc))
        time.sleep(STARTUP_DELAY)

    #  start frontend 
    print()
    print(f"{BOLD}  Starting frontend…{RESET}")
    print()

    frontend_proc = start_frontend()
    if frontend_proc:
        running_processes.append(("Frontend", frontend_proc))

    if not running_processes:
        err("No services started successfully — exiting.")
        sys.exit(1)

    print_summary()

    #  wait for signals 
    try:
        while True:
            # check if any process died unexpectedly and warn
            for name, proc in running_processes:
                if proc.poll() is not None:
                    warn(f"{name} exited unexpectedly (return code {proc.returncode})")
                    running_processes.remove((name, proc))
                    break
            time.sleep(3)
    except KeyboardInterrupt:
        shutdown_all()


if __name__ == "__main__":
    main()