#commands for fast api setup
#pip install fastapi uvicorn
#python -m fastapi dev BaseNetworkInfo.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from enum import Enum
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"Hello": "World"}

#networking section
import subprocess # system commands for linux
import statistics # helps calculate jitter 
import re # extracts numbers using regex

#enum classes for ranging whats good ms and filtering them for an if or else statement
class LatencyQuality(str, Enum):
    excellent = "excellent (0-20ms)"
    good = " good (20-40ms)"
    moderate = "moderate (40-60ms)"
    poor = "ok (60-100ms)"
    unstable = "poor (100ms+)"

class JitterQuality(str, Enum):
    excellent = "excellent (0-5ms)"
    good = "good (5-10ms)"
    moderate = "moderate (10-20ms)"
    poor = "poor (20-30ms)"
    unstable = "unstable (30ms+)"


def get_latency_quality(latency: float) -> LatencyQuality:
    if latency <= 20:
        return LatencyQuality.excellent
    elif latency <= 40:
        return LatencyQuality.good
    elif latency <= 60:
        return LatencyQuality.moderate
    elif latency <= 100:
        return LatencyQuality.poor
    else:
        return LatencyQuality.unstable


def get_jitter_quality(jitter: float) -> JitterQuality:
    if jitter <= 5:
        return JitterQuality.excellent
    elif jitter <= 10:
        return JitterQuality.good
    elif jitter <= 20:
        return JitterQuality.moderate
    elif jitter <= 30:
        return JitterQuality.poor
    else:
        return JitterQuality.unstable







# vibe code section start
# as i had no on linux how to convert normal bytes to just kb
def get_network_throughput():
    try:
        result = subprocess.run(
            [
                "curl",
                "-o", "/dev/null",
                "-s",
                "-w", "%{speed_download}",
                "https://speed.hetzner.de/100MB.bin"
            ],
            capture_output=True,
            text=True
        )

        # gets the output from the console and stores it 
        speed_bytes_per_sec = float(result.stdout.strip())

        # convert bytes/sec → kilobits/sec
        throughput_kbps = (speed_bytes_per_sec * 8) / 1000

        return round(throughput_kbps, 2)

    except Exception:
        return 0
# vibe code section end 












# count is the number of pings also 8.8.8.8 host is just google 
# the host will and might be changed to be the docker container in the future
# that means the host that gets pinged should have its variable docker host
# address get changed from the GUI
def get_network_status(host="8.8.8.8", count=5):

    #Linux system ping that pings the host 5 times -c is count command btw
    # subprcess is used to run the command on linux and send it back as 
    # a readable string 
    result = subprocess.run(
        ["ping", "-c", str(count), host],
        capture_output=True,
        text=True
    )

    #gets the output from linux console  via standard output
    output = result.stdout

    #looks for time= then the digits and some more as well as any floating point digits and whatever else via * wildcards
    # regex expression variable list to basically rip out time from the stdout and store it in there
    times = [float(x) for x in re.findall(r"time=(\d+\.?\d*)", output)]

    if not times:
        return {"error": "Could not measure latency"}
    # error for incase we dont get anything 
    
    total = 0
    counter = 0

    for t in times:
        total += t
        counter += 1

    #simple math for dividing the total number of pings  ie total ms delay / num of pings 
    avg_latency = total / counter

    # jitter = variation in latency using statstics to get
    # avg,deviation and variance and then checking the times variable list
    # and also check to see if anything is in there as well
    jitter = statistics.stdev(times) if len(times) > 1 else 0

    # get the quality ratings to see if its good or bad 
    latency_quality = get_latency_quality(avg_latency)
    jitter_quality = get_jitter_quality(jitter)

    # packet loss calculation
    received = len(times) # comparing to see how many packets we got and saved
    sent = count # and then subtracting it from the number of pings we sent 
    # then dividing it and getting it up to a percentage and rounding 
    packet_loss_percent = round(((sent - received) / sent) * 100, 2) 

    # vibe coded function and variable 
    throughput_kbps = get_network_throughput()

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")# using datetime to get the current time
    # from the system and then formatting it yyyy-mm-dd and then hour,minutes and seconds

    return {

        # existing info which might get merged or removed a bit
        "host": host,
        "pings": times,
        "average_latency_ms": round(avg_latency, 2),
        "latency_quality": latency_quality,
        "jitter_ms": round(jitter, 2),
        "jitter_quality": jitter_quality,

        # new metrics for project database schema for when the data base is
        # setup later 
        "container_id": "LinuxMachineHere",
        "latency_ms": round(avg_latency, 2),
        "packet_loss_percent": packet_loss_percent,
        "throughput_kbps": throughput_kbps,
        "timestamp": timestamp
    }


@app.get("/network")
def network_info():
    return get_network_status()

