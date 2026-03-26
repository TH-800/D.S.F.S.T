# Memory (RAM) Stress Injection using stress-ng

#commands for fast api setup
#pip install fastapi uvicorn psutil
#pip install "fastapi[standard]"
#sudo apt install stress-ng 

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import subprocess
from datetime import datetime
import os
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONTAINER_ID = "LinuxMachineHere"

  #track memory stress process
memory_process = None

@app.get("/")
def read_root():
    return {"message": "Memory Stress Injection API"}


def inject_memory_stress(memory_mb: int, duration: int):
    # Inject RAM stress using stress-ng
    # memory_mb: amount of RAM to restrict for a bit (max 4096 MB) in 24kb 
    # duration: time in seconds

    global memory_process

    # Prevent overloading host machine because were on docker and vmware 
    if memory_mb < 64 or memory_mb > 4096:
        return {"error": "Memory must be between 64MB and 4096MB (4GB limit)"}

    if duration < 1 or duration > 300:
        return {"error": "Duration must be between 1 and 300 seconds"}

    # prevents multiple memory stress injections at once and only have on process at a time
    if memory_process and memory_process.poll() is None:
        return {"error": "Memory stress already running"}

    # commands stored in a list string variable so they can be executed in the
    # shell when the script runs which then runs the requested memory stress
    # stress-ng --vm 1 --vm-bytes 1024M --timeout 30s --vm-keep remove this comment later or keep it in
    # as we can use this for testing in bash shell 

   # get number of CPU cores (fallback to 1 if None)
    cpu_cores = os.cpu_count() or 1

    # use 1/4 of the  workers to prevent the rest of the cpus going crazy and spread em out 
    # because this aint a cpu stress its a memory stress test but it does both and this command is silly
    workers = max(1, cpu_cores // 4)

    #gets the amount of memory and divides it among the workers ie cpus to cycle the ram 
    # so if we got 8 cpu cores and 1000mb of ram to test it would be 2 cpus getting the ram to cycle in 500mb chunks 
    memory_per_worker = max(1, memory_mb // workers)
    command = [
    "stress-ng",
    "--vm", str(workers), # vm starts the worker process/cpu 
    "--vm-bytes", f"{memory_per_worker}M",  # memory in bytes given to each worker 
    "--vm-method", "write64", # write 64 is repeated alot in order to simulate ram stress test (DONT USE WRITE. USE WRITE64)
    "--timeout", f"{duration}s",
    "--vm-keep" #keeps the ram in the test instead of freeing it so we dont constantly add and remove the ram 
    ]

    # Start stress test
    try:
        memory_process = subprocess.Popen(command)#injects the command and stores the process
    except FileNotFoundError:
        return {"error": "stress-ng not found please install it 'sudo apt install stress-ng'"}
    except Exception as error:
        return {"error": str(error)}

    return {
        "container_id": CONTAINER_ID,
        "memory_requested_mb": memory_mb,
        "duration_seconds": duration,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }


@app.post("/inject/memory")
def api_memory_stress(memory_mb: int, duration: int = 30):
    return inject_memory_stress(memory_mb, duration)


@app.post("/reset/memory")
def reset_memory_stress():
    
    #Stops only the current stress-ng memory worker instead of all of them
    
    global memory_process

    if memory_process and memory_process.poll() is None:
        memory_process.terminate()
        memory_process.wait(timeout=5)
        memory_process = None
        return {"message": "Memory stress stopped"}

    return {"message": "No memory stress running"}
