#commands for fast api setup
#pip install fastapi uvicorn psutil
#python -m fastapi dev LinuxMemoryStatus.py

from fastapi import FastAPI
from datetime import datetime
import psutil # import for reading processes,cpu,memory and system data and etc

app = FastAPI()

@app.get("/")
def read_root():
    return {"HELLO!": " Memory Status For The API"}

# memory monitoring section for linux systems no windows this time 
# uses psutil to check memory usage

def get_memory_status(container_id="LinuxMachineHere"):
    # update here when docker is setup
    # so when docker is setup it can dynamically change via the GUI for what machine 
    # the script is gonna run on 

    memory = psutil.virtual_memory() # the psutill command is a fine ol cross platform bit of syntax for
    # cross platform memory reading also it reads the amount of memory/ram in the system 

    memory_used_mb = round(memory.used / (1024 * 1024), 2) # rounding up the amount of memory we get into 
    memory_percent = memory.percent # returns the total percent of memory

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") # using datetime to get the current time
    # from the system and then formatting it yyyy-mm-dd and then hour,minutes and seconds

    # json return format
    return {
        "container_id": container_id,
        "memory_used_mb": memory_used_mb,
        "memory_percent": memory_percent,
        "timestamp": timestamp
    }


@app.get("/memory")
def memory_info():
    return get_memory_status()
