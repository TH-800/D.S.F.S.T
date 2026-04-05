#commands for fast api setup
#pip install fastapi uvicorn psutil
#python -m fastapi dev LinuxCpuStatus.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import psutil # import for reading processes,cpu,memory and system data and etc

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
    return {"HELLO! ": " CPU Status For The API"}

# cpu monitoring section for linux systems no windows this time 
# uses psutil to check cpu usage

def get_cpu_status(container_id="LinuxMachineHere"): # update here when docker is setup
    # so when docker is setup it can dynamically change via the GUI for what machine 
    # the script is gonna run on 

    cpu_usage = psutil.cpu_percent(interval=1) # the psutill command is a fine ol cross platform bit of syntax for
    # cross platform cpu reading also it reads the cpu percentage of use every 1 or so seconds i think

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")# using datetime to get the current time
    # from the system and then formatting it yyyy-mm-dd and then hour,minutes and seconds

    # json return format
    return {
        "container_id": container_id,
        "cpu_usage_percent": cpu_usage,
        "timestamp": timestamp
    }


@app.get("/cpu")
def cpu_info():
    return get_cpu_status()

