# Network Packet Loss Injection API

# Commands for FastAPI setup
# pip install fastapi uvicorn psutil
# pip install "fastapi[standard]"
# python -m fastapi dev PacketLossInjection.py

from fastapi import FastAPI
import subprocess  # for running external shell commands
from datetime import datetime

app = FastAPI()

NETWORK_INTERFACE = "ens33"  # First ethernet interface; change if different
CONTAINER_ID = "LinuxMachineHere"

@app.get("/")
def read_root():
    return {"message": "Packet Loss Injection API", "interface": NETWORK_INTERFACE}

def inject_packet_loss(loss_percent: int):
    """
    Inject packet loss using tc/netem.
    loss_percent: 0-50%
    """

    if loss_percent < 0 or loss_percent > 50:
        return {"error": "Packet loss must be between 0 and 50 percent"}

    # commands stored in a list so they can be executed in the shell
    command = [
        "sudo",
        "tc",           # traffic control
        "qdisc",        # queueing discipline
        "replace",      # replace rule
        "dev",
        NETWORK_INTERFACE,
        "root",
        "netem",        # emulate network conditions
        "loss",
        f"{loss_percent}%"
    ]

    subprocess.run(command, check=True)  # inject packet loss

    return {
        "container_id": CONTAINER_ID,
        "packet_loss_percent": loss_percent,
        "interface": NETWORK_INTERFACE,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.post("/inject/packetloss/{loss_percent}")
def api_packet_loss(loss_percent: int):
    return inject_packet_loss(loss_percent)

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
    ], check=True)

    return {"message": "Network conditions reset"}