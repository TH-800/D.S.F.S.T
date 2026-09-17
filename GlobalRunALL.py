# Runs the main D.S.F.S.T app scripts from one script.
# This assumes Docker, Python dependencies, Node dependencies, .env,
# and the database setup have already been setup if not go do it.

import subprocess# subprocess lets us  start and control other programs/processes.

import sys #runs python system commands thats going to let us execute commands on linux

import time
# time provides time

# subprocess.run() waits until the command itself finishes.
# Because Docker uses -d the containers continue running
# in the background after the Docker command finishes.

print("Docker starting up")

subprocess.run(["docker", "compose", "up", "-d"],check=True) # check = true is for in case something fails we know by having python check if it worked or not 

# subprocess.Popen() starts the program but DOES NOT wait for it to finish.
# GlobalRunALL.py continues running while RunALL.py runs at the same.

# RunALL.py RUNS ALL THE SCRIPTS FOR INJECTION AND ETC 
#this script runs docker because  i didnt add that in last time

# sys.executable makes sure RunALL.py uses the same Python interpreter
# that is currently ALSO running GlobalRunALL.py.
print("Starting RunALL.py")

runAll = subprocess.Popen(
    [sys.executable, "RunALL.py"]
)


# Pause GlobalRunALL.py for 8 seconds so everything can start on the other side
# as some VMs are slower then others so they need time
time.sleep(8)



# Popen is used again because metrics_writer.py needs to stay running at the same time as RunALL.py.
print("Starting metrics_writer.py")

metrics_writer = subprocess.Popen(
    [sys.executable, "metrics_writer.py"]
)


# Port 3000 is the gui dashboard 
# Ports 8000-8010 are backend API services and as a note dont change anything at all 
# or else the ports break
print("D.S.F.S.T is running.")
print("Open http://localhost:3000")
print("Press Ctrl+C to stop the app.")

