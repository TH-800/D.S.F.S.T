#CPU Stress Injection using stress-ng

#commands for fast api setup
#pip install fastapi uvicorn psutil
#pip install "fastapi[standard]"
#sudo apt install stress-ng 

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import subprocess # import for running external commands via python 
# so we can pass shell commands to the console 
import os # import for working with system level operations 
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONTAINER_ID = "LinuxMachineHere"

@app.get("/")
def read_root():
    return {"message": "CPU Stress Injection API"}

def inject_cpu_stress(cpu_percent: int, duration: int):
   # Inject CPU stress using stress-ng.
   # cpu_percent: 1-65% recommended
   # duration: in seconds

    # Prevent overloading host machine
    if cpu_percent < 1 or cpu_percent > 65:
        return {"error": "CPU load must be between 1% and 65% to prevent host failure"}

    cpu_cores = os.cpu_count() or 1 #small fix so incase somehow there are like 0 cpu cores it defaults 1 without breaking anything i hope
    
    # gets the number of cpu cores and divides them into a percentage 
    workers = max(1, round(cpu_cores * (cpu_percent / 100)))

    # commands stored in a list string variable so they can be executed in the
    # shell when the script runs which then runs the requested CPU stress
    # and then shoves the stress into one or more of the cpu cores over loading them
    command = [
        "stress-ng", # stress test a system component which also needs the apt install
        "--cpu",
        str(workers),
        "--timeout", # how long the cpu is going to be stressed for 
        f"{duration}s"
    ]

    # Start stress test
    try:
        subprocess.Popen(command, start_new_session=True)#injects the command 
    except FileNotFoundError:
        return {"error": "stress-ng not found please install it 'sudo apt install stress-ng'"}
    except Exception as error:
        return {"error": str(error)}

    return {
        "container_id": CONTAINER_ID,
        "cpu_requested_percent": cpu_percent,
        "cpu_workers_started": workers,
        "duration_seconds": duration,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.post("/inject/cpu")
def api_cpu_stress(cpu_percent: int, duration: int = 30):
    return inject_cpu_stress(cpu_percent, duration)

@app.post("/reset/cpu")
def reset_cpu_stress():
    
    #Stops all stress-ng CPU workers.
    
    subprocess.run(["sudo", "pkill", "-f", "stress-ng"], check=True)
    return {"message": "CPU stress stopped"}
