from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import subprocess
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SET YOUR INTERFACE MANUALLY OR USE DYNAMIC DETECTION
NETWORK_INTERFACE = "ens33"  # ens33 is the first ethernet interface; change if different
CONTAINER_ID = "LinuxMachineHere"

@app.get("/")
def read_root():
    return {
        "message": "Network Latency Injection API",
        "interface": NETWORK_INTERFACE
    }

def inject_latency(delay_ms: int):
    """
    Inject a latency in milliseconds using tc/netem.
    delay_ms: 0-500ms
    """

    if delay_ms < 0 or delay_ms > 500:
        return {"error": "Latency must be between 0 and 500 ms"}

    # commands stored in a list so they can be executed in the shell
    command = [
        "sudo",
        "tc",           # traffic control
        "qdisc",        # queueing discipline for scheduling network packets
        "replace",      # replace existing rule
        "dev",
        NETWORK_INTERFACE,
        "root",
        "netem",        # emulate network conditions
        "delay",
        f"{delay_ms}ms"
    ]

    subprocess.run(command, check=True)  # inject the latency

    return {
        "container_id": CONTAINER_ID,
        "latency_injected_ms": delay_ms,
        "interface": NETWORK_INTERFACE,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.post("/inject/latency/{delay_ms}")
def api_latency(delay_ms: int):
    return inject_latency(delay_ms)

@app.post("/reset/network")
def reset_network():
    """
    Reset network to normal by removing tc/netem rules.
    """
    subprocess.run([
        "sudo",
        "tc",
        "qdisc",
        "del",
        "dev",
        NETWORK_INTERFACE,
        "root"
    ], capture_output=True)  # exit code 2 = no rule exists, that is fine
    if result.returncode not in (0, 2):
        return {"error": f"tc del failed: exit {result.returncode}"}

    return {"message": "Network conditions reset"}
