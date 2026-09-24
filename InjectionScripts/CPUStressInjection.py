#CPU Stress Injection using stress-ng

#commands for fast api setup
#pip install fastapi uvicorn psutil
#pip install "fastapi[standard]"
#sudo apt install stress-ng 

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import subprocess # import for running external commands via python 
# so we can pass shell commands to the console 
import os # import for working with system level operations 
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


@app.middleware("http")
async def protect_local_api(request, call_next):
    allowed = {"http://localhost:3000", "http://127.0.0.1:3000"}
    origin = request.headers.get("origin")
    host = request.url.hostname
    if host not in ("localhost", "127.0.0.1") or (origin and origin not in allowed):
        return JSONResponse({"detail": "Local dashboard access only"}, status_code=403)
    return await call_next(request)

CONTAINER_ID = "host"

# track cpu stress process so we dont kill all stress-ng processes and make a variable to store it in
cpu_process = None

@app.get("/")
def read_root():
    return {"message": "CPU Stress Injection API"}

def inject_cpu_stress(cpu_percent: int, duration: int):
   # Inject CPU stress using stress-ng.
   # cpu_percent: 1-65% recommended
   # duration: in seconds

    global cpu_process

    #checking for errors and seeing if anything is already running 
    # and if not then run the commands and try statement 
    # Prevent overloading host machine
    if cpu_percent < 1 or cpu_percent > 65:
        return {"error": "CPU load must be between 1% and 65% to prevent host failure"}

    if duration < 1 or duration > 300:
        return {"error": "Duration must be between 1 and 300 seconds"}

    # prevents multiple cpu stress injections at once
    if cpu_process and cpu_process.poll() is None:
        return {"error": "CPU stress already running"}

    cpu_cores = os.cpu_count() or 1 #small fix so incase somehow there are like 0 cpu cores it defaults 1 without breaking anything i hope
    
    # gets the number of cpu cores and divides them into a percentage and then finds the number of cpus to test out
    workers = max(1, round(cpu_cores * (cpu_percent / 100)))

    # commands stored in a list string variable so they can be executed in the
    # shell when the script runs which then runs the requested CPU stress
    # and then shoves the stress into one or more of the cpu cores over loading them
    command = [
        "stress-ng", # stress test a system component which also needs the apt install
        "--cpu",
        str(workers), # str to convert from a number to a string so it can be used in the shell
        "--timeout", # how long the cpu is going to be stressed for 
        f"{duration}s" # duration time 
    ]

    # Start stress test
    try:
        cpu_process = subprocess.Popen(command)#injects the command and stores the process
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
    result = inject_cpu_stress(cpu_percent, duration)
    if "error" in result:
        raise HTTPException(status_code=409 if "already running" in result["error"] else 422,
                            detail=result["error"])
    return result

@app.post("/reset/cpu")
def reset_cpu_stress():
    
    #Stops only the current stress-ng CPU worker instead of all of them
    
    global cpu_process

    if cpu_process and cpu_process.poll() is None:
        cpu_process.kill()  # SIGKILL — terminate() can leave stress-ng running, kill() doesn't SO DONT USE KILL()
        try:
            cpu_process.wait(timeout=3)
        except Exception:
            pass  # if it times out, it'll be cleaned up by the OS and if does not i dont know then
        cpu_process = None
        return {"message": "CPU stress stopped"}

    return {"message": "No CPU stress running"}
