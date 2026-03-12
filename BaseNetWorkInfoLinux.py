#commands for fast api setup
#pip install fastapi uvicorn or  pip install "fastapi[standard]" for installing fastAPI via vscode 
#python -m fastapi dev BaseNetWorkInfo.py for running the server also make sure you cd into the directory that has the BaseNetWorkInfo.py


from fastapi import FastAPI
from enum import Enum

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

#networking section for seeing if i can get a mock setup for the api on LINUX as its currently untested since my VMware aint seutp yet

import subprocess # system commands for linux
import statistics # calculate jitter 
import re # extracts numbers using regex


#enum classes for ranging whats good ms

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


def get_network_status(host="8.8.8.8", count=5): # count is the number of pings also 8.8.8.8 host is just google 
    #(host = "youtube.com", count=5)

    #Linux system ping that pings the host 5 times -c is count command
    result = subprocess.run(["ping", "-c", str(count), host], # 
                            
        capture_output=True,
        text=True
    )

    output = result.stdout
    #gets the output from linux console  via standard output
    #PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
    #64 bytes from 8.8.8.8: icmp_seq=1 ttl=116 time=14.2 ms
    
    times = [float(x) for x in re.findall(r"time=(\d+\.?\d*)", output)]  #looks for time= then the digits and some more as well as any floating point digits and whatever else via * wildcards
    # regex expression variable list to basically rip out time from the stdout and store it in there
    
    if not times:
        return {"error": "Could not measure latency"}
    # error for incase we dont get anything 


    total = 0 
    count = 0
    for t in times:
        total += t
        count += 1 
 
        
    avg_latency = total / count 
    #simple math for dividing the total number of pings  ie total ms delay / num of pings 

    # jitter = variation in latency
    jitter = statistics.stdev(times) if len(times) > 1 else 0

    # get the quality ratings to see if its good or bad 
    latency_quality = get_latency_quality(avg_latency)
    jitter_quality = get_jitter_quality(jitter)

# json return format 
    return {
        "host": host,
        "pings": times,
        "average_latency_ms": round(avg_latency, 2), # the 2 is for decimals 
        "latency_quality": latency_quality,
        "jitter_ms": round(jitter, 2),
        "jitter_quality": jitter_quality
    }


@app.get("/network")
def network_info():
    return get_network_status()
