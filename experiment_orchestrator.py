# experiment_orchestrator.py
# Task 2.5      Experiment Orchestrator with State Machine Logic
# Task 3.1      FastAPI endpoints to manage experiments (create / start / stop)
#
# Runs on port 8009.
#
# Setup:
#   pip install fastapi uvicorn pymongo redis python-dotenv requests
#
# Run:
#   python -m uvicorn experiment_orchestrator:app --host 127.0.0.1 --port 8009 --reload
#
# State machine:
#   idle  - running - stopping - complete - idle
#
# Redis keys (with 2 hour TTL so stale state doesn't linger):
#   dsft:state               idle | running | stopping | complete
#   dsft:active_experiment   experiment_id string
#
# Endpoints:
#   GET  /state                        current state machine state + active experiment
#   POST /experiments                  create a new experiment (stores in MongoDB)
#   POST /experiments/{id}/start       start the injection for a created experiment
#   POST /experiments/{id}/stop        stop a specific running experiment
#   POST /emergency-stop               cancel ALL active injections within 20 seconds
 
import asyncio
import uuid
import os
import sys
from datetime import datetime, timezone
from typing import Optional
 
import redis
import requests
from dotenv import load_dotenv
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import PyMongoError
 
# find .env relative to this script so it works regardless of where uvicorn is launched
# try the script's own directory first, then fall back to cwd
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=True)
load_dotenv(override=False)  # fallback: picks up .env in cwd if above didn't load it
 
   # Config
    
MONGO_URI = os.getenv("MONGO_URI",     "mongodb://127.0.0.1:27017/")
MONGO_DB  = os.getenv("MONGO_DB_NAME", "dsfst")
 
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB",   "0"))
 
# Redis TTL for state keys 2 hours to prevents stale "running" state after a crash
STATE_TTL_SECONDS = 7200
 
# injection script URLs each script runs on its own port
INJECTION_URLS = {
    "cpu":          "http://127.0.0.1:8004",
    "latency":      "http://127.0.0.1:8005",
    "packet_loss":  "http://127.0.0.1:8006",
    "memory":       "http://127.0.0.1:8007",
}
 
# reset endpoints to call on emergency stop  we hit all of these regardless
# of what is currently running so nothing is left injecting
RESET_ENDPOINTS = [
    ("cpu reset",          "http://127.0.0.1:8004/reset/cpu"),
    ("network reset",      "http://127.0.0.1:8005/reset/network"),
    ("packet loss reset",  "http://127.0.0.1:8006/reset/network"),
    ("memory reset",       "http://127.0.0.1:8007/reset/memory"),
]
 
# emergency stop must complete within this many seconds
EMERGENCY_STOP_TIMEOUT = 20
 
   # App setup
    
app = FastAPI(title="D.S.F.S.T Experiment Orchestrator", version="1.0.0")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
   # DB / cache connections (opened once)
    
def _get_mongo():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    return client[MONGO_DB]
 
 
def _get_redis() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=3,
    )
 
   # State machine      Redis-backed
    
class StateMachine:
    """
    Manages the experiment lifecycle state in Redis.
 
    States:
        idle           no experiment running, safe to start one
        running        injection is active
        stopping       stop has been requested, waiting for resets to complete
        complete       injection finished, results available; next start resets to idle
    """
 
    STATE_KEY      = "dsft:state"
    ACTIVE_EXP_KEY = "dsft:active_experiment"
 
    # allowed transitions: current_state to a set of valid next states
    TRANSITIONS = {
        "idle":     {"running"},
        "running":  {"stopping"},
        "stopping": {"complete", "idle"},
        "complete": {"idle", "running"},   # allow immediate re-run
    }
 
    def __init__(self, r: redis.Redis):
        self._r = r
 
    def get(self) -> str:
        state = self._r.get(self.STATE_KEY)
        return state if state else "idle"
 
    def get_active_experiment(self) -> Optional[str]:
        return self._r.get(self.ACTIVE_EXP_KEY)
 
    def transition(self, new_state: str, experiment_id: Optional[str] = None):
        current = self.get()
        if new_state not in self.TRANSITIONS.get(current, set()):
            raise ValueError(
                f"Invalid state transition: {current} → {new_state}. "
                f"Allowed from {current}: {self.TRANSITIONS.get(current, set())}"
            )
        pipe = self._r.pipeline()
        pipe.set(self.STATE_KEY, new_state, ex=STATE_TTL_SECONDS)
        if experiment_id:
            pipe.set(self.ACTIVE_EXP_KEY, experiment_id, ex=STATE_TTL_SECONDS)
        elif new_state in ("idle", "complete"):
            pipe.delete(self.ACTIVE_EXP_KEY)
        pipe.execute()
 
    def force_idle(self):
        """Used after emergency stop to unconditionally reset state."""
        pipe = self._r.pipeline()
        pipe.set(self.STATE_KEY, "idle", ex=STATE_TTL_SECONDS)
        pipe.delete(self.ACTIVE_EXP_KEY)
        pipe.execute()
 
   # MongoDB helpers
    
def _log_event(db, experiment_id: str, event_type: str, message: str, details: dict = None):
    db["logs"].insert_one({
        "log_id":        str(uuid.uuid4()),
        "experiment_id": experiment_id,
        "event_type":    event_type,
        "message":       message,
        "timestamp":     datetime.now(timezone.utc),
        "details":       details or {},
    })
 
 
def _upsert_experiment(db, experiment_id: str, fields: dict):
    db["experiments"].update_one(
        {"experiment_id": experiment_id},
        {"$set": fields},
        upsert=True,
    )
 
   # Pydantic request models
    
class CreateExperimentRequest(BaseModel):
    name:             Optional[str]  = None
    failure_type:     str                          # cpu | latency | packet_loss | memory
    target_container: Optional[str]  = "LinuxMachineHere"
    parameters:       dict           = {}
 
class StartExperimentRequest(BaseModel):
    # optional override      if the experiment was created with parameters these are
    # already stored in MongoDB, but the caller can override them here
    parameters: Optional[dict] = None
 
   # Injection call helpers
    
def _call_injection(failure_type: str, parameters: dict) -> dict:
    """
    Calls the correct injection script endpoint based on failure_type.
    Returns the response JSON from the injection script.
    Raises requests.RequestException on connection failure.
    """
    base = INJECTION_URLS.get(failure_type)
    if not base:
        raise ValueError(f"Unknown failure_type: {failure_type!r}. "
                         f"Must be one of: {list(INJECTION_URLS.keys())}")
 
    if failure_type == "cpu":
        cpu_percent = parameters.get("cpu_percent", 50)
        duration    = parameters.get("duration_seconds", 30)
        url = f"{base}/inject/cpu?cpu_percent={cpu_percent}&duration={duration}"
 
    elif failure_type == "latency":
        delay_ms = parameters.get("latency_ms", 100)
        url = f"{base}/inject/latency/{delay_ms}"
 
    elif failure_type == "packet_loss":
        loss_pct = parameters.get("packet_loss_percent", 10)
        url = f"{base}/inject/packetloss/{loss_pct}"
 
    elif failure_type == "memory":
        memory_mb = parameters.get("memory_mb", 512)
        duration  = parameters.get("duration_seconds", 30)
        url = f"{base}/inject/memory?memory_mb={memory_mb}&duration={duration}"
 
    else:
        raise ValueError(f"Unhandled failure_type: {failure_type!r}")
 
    resp = requests.post(url, timeout=10)
    resp.raise_for_status()
    return resp.json()
 
 
def _call_reset(failure_type: str) -> dict:
    """Calls the reset endpoint for a specific failure type."""
    base = INJECTION_URLS.get(failure_type)
    if not base:
        return {"error": f"Unknown failure_type: {failure_type}"}
 
    if failure_type == "cpu":
        url = f"{base}/reset/cpu"
    elif failure_type in ("latency", "packet_loss"):
        url = f"{base}/reset/network"
    elif failure_type == "memory":
        url = f"{base}/reset/memory"
    else:
        return {"error": f"No reset endpoint for {failure_type}"}
 
    try:
        resp = requests.post(url, timeout=10)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}
 
   # API endpoints
    
@app.get("/state")
def get_state():
    """
    Returns the current state machine state and active experiment ID.
    Useful for the frontend to poll and know if it's safe to start a new experiment.
    """
    try:
        r  = _get_redis()
        sm = StateMachine(r)
        return {
            "state":                sm.get(),
            "active_experiment_id": sm.get_active_experiment(),
            "timestamp":            datetime.now(timezone.utc).isoformat(),
        }
    except redis.RedisError as e:
        # if Redis is down, fall back gracefully rather than crashing the whole service
        return {
            "state":     "unknown",
            "error":     f"Redis unavailable: {e}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
 
 
@app.post("/experiments", status_code=201)
def create_experiment(body: CreateExperimentRequest):
    """
    POST /experiments
    Creates a new experiment document in MongoDB with status 'created'.
    Does NOT start the injection yet      call /experiments/{id}/start for that.
 
    Returns:
        { "experiment_id": "...", "status": "created" }
    """
    db = _get_mongo()
    experiment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
 
    name = body.name or f"{body.failure_type}      {now.strftime('%Y-%m-%d %H:%M')}"
 
    doc = {
        "experiment_id":    experiment_id,
        "name":             name,
        "failure_type":     body.failure_type,
        "target_container": body.target_container,
        "parameters":       body.parameters,
        "status":           "created",
        "created_at":       now,
        "started_at":       None,
        "ended_at":         None,
    }
 
    try:
        db["experiments"].insert_one(doc)
        _log_event(db, experiment_id, "info",
                   f"Experiment created: {name}",
                   {"failure_type": body.failure_type, "parameters": body.parameters})
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"MongoDB error: {e}")
 
    return {"experiment_id": experiment_id, "status": "created", "name": name}
 
 
@app.post("/experiments/{experiment_id}/start")
def start_experiment(experiment_id: str, body: StartExperimentRequest = StartExperimentRequest()):
    """
    POST /experiments/{id}/start
    Starts the failure injection for an already-created experiment.
    Transitions state machine: idle/complete → running.
 
    Steps:
        1. Load the experiment from MongoDB
        2. Check state machine is in a startable state
        3. Call the injection script
        4. Update MongoDB status to 'running'
        5. Transition state machine to 'running'
        6. Log the event
    """
    db = _get_mongo()
 
    #   load experiment from MongoDB  
    try:
        exp = db["experiments"].find_one({"experiment_id": experiment_id}, {"_id": 0})
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"MongoDB error: {e}")
 
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
 
    if exp.get("status") == "running":
        raise HTTPException(status_code=409, detail="Experiment is already running")
 
    #   check state machine  
    try:
        r  = _get_redis()
        sm = StateMachine(r)
        current_state = sm.get()
    except redis.RedisError:
        # Redis down      allow the start to proceed without state tracking
        sm = None
        current_state = "idle"
 
    if current_state == "running":
        active_id = sm.get_active_experiment() if sm else "unknown"
        raise HTTPException(
            status_code=409,
            detail=f"Another experiment ({active_id}) is already running. "
                   f"Stop it first or call /emergency-stop.",
        )
 
    # use caller-supplied parameters if provided, otherwise use what's stored
    parameters = body.parameters if body.parameters else exp.get("parameters", {})
 
    #   call the injection script  
    failure_type = exp.get("failure_type")
    try:
        result = _call_injection(failure_type, parameters)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to the {failure_type} injection script. "
                   f"Make sure RunAll.py is running.",
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Injection script error: {e}")
 
    # check if the injection script itself returned an error body
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
 
    #   update MongoDB  
    now = datetime.now(timezone.utc)
    try:
        _upsert_experiment(db, experiment_id, {
            "status":     "running",
            "started_at": now,
            "ended_at":   None,
            "parameters": parameters,
        })
        _log_event(db, experiment_id, "injection_started",
                   f"Injection started: {failure_type}",
                   {"parameters": parameters, "injection_response": result})
    except PyMongoError as e:
        # injection is running but we couldn't log warn but don't crash
        print(f"[orchestrator] MongoDB update failed after injection start: {e}")
 
    #   transition state machine  
    if sm:
        try:
            sm.transition("running", experiment_id=experiment_id)
        except (ValueError, redis.RedisError) as e:
            # state machine error shouldn't stop us  injection is already running
            print(f"[orchestrator] State machine transition failed: {e}")
 
    return {
        "experiment_id":    experiment_id,
        "status":           "running",
        "failure_type":     failure_type,
        "parameters":       parameters,
        "started_at":       now.isoformat(),
        "injection_result": result,
    }
 
 
@app.post("/experiments/{experiment_id}/stop")
def stop_experiment(experiment_id: str):
    """
    POST /experiments/{id}/stop
    Stops a running experiment by calling the appropriate reset endpoint.
    Transitions state machine: running → stopping → complete.
 
    Steps: to do this ie notes for anyone reading this 
        1. Load the experiment from MongoDB
        2. Call the reset endpoint for its failure_type
        3. Update MongoDB status to 'completed'
        4. Transition state machine to 'complete'
        5. Log the event
    """
    db = _get_mongo()
 
    try:
        exp = db["experiments"].find_one({"experiment_id": experiment_id}, {"_id": 0})
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"MongoDB error: {e}")
 
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
 
    if exp.get("status") != "running":
        raise HTTPException(
            status_code=409,
            detail=f"Experiment status is '{exp.get('status')}', not 'running'. Nothing to stop.",
        )
 
    failure_type = exp.get("failure_type")
    now          = datetime.now(timezone.utc)
 
    #   transition to stopping  
    try:
        r  = _get_redis()
        sm = StateMachine(r)
        sm.transition("stopping", experiment_id=experiment_id)
    except (ValueError, redis.RedisError) as e:
        sm = None
        print(f"[orchestrator] Could not transition to stopping: {e}")
 
    #   call reset  
    reset_result = _call_reset(failure_type)
 
    #   update MongoDB  
    try:
        _upsert_experiment(db, experiment_id, {
            "status":   "completed",
            "ended_at": now,
        })
        _log_event(db, experiment_id, "injection_stopped",
                   f"Injection stopped: {failure_type}",
                   {"reset_result": reset_result})
    except PyMongoError as e:
        print(f"[orchestrator] MongoDB update failed after stop: {e}")
 
    #   transition to complete  
    if sm:
        try:
            sm.transition("complete")
        except (ValueError, redis.RedisError) as e:
            print(f"[orchestrator] Could not transition to complete: {e}")
 
    return {
        "experiment_id": experiment_id,
        "status":        "completed",
        "failure_type":  failure_type,
        "ended_at":      now.isoformat(),
        "reset_result":  reset_result,
    }
 
 
@app.post("/emergency-stop")
def emergency_stop():
    """
     Emergency stop function.
    Cancels ALL active injections within 20 seconds regardless of type.
    Calls every reset endpoint concurrently then marks any active experiment
    as stopped in MongoDB.
 
    This is the big red button      it doesn't care what is running, it stops everything.
    """
    db  = _get_mongo()
    now = datetime.now(timezone.utc)
 
    #   call all reset endpoints concurrently using a thread pool  
    # asyncio is not available here in sync context so we use concurrent.futures
    import concurrent.futures
 
    results = {}
 
    def _reset_one(label: str, url: str) -> tuple[str, dict]:
        try:
            r = requests.post(url, timeout=EMERGENCY_STOP_TIMEOUT - 2)
            return label, r.json()
        except requests.exceptions.ConnectionError:
            return label, {"status": "service offline"}
        except Exception as e:
            return label, {"error": str(e)}
 
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(RESET_ENDPOINTS)) as pool:
        futures = [pool.submit(_reset_one, label, url) for label, url in RESET_ENDPOINTS]
        # wait for all with the 20-second hard deadline
        done, _ = concurrent.futures.wait(
            futures,
            timeout=EMERGENCY_STOP_TIMEOUT,
        )
        for f in done:
            label, result = f.result()
            results[label] = result
 
    #   mark any currently running experiment as stopped  
    stopped_experiment_id = None
    try:
        r  = _get_redis()
        sm = StateMachine(r)
        stopped_experiment_id = sm.get_active_experiment()
        sm.force_idle()
    except redis.RedisError as e:
        print(f"[orchestrator] Redis unavailable during emergency stop: {e}")
        # fall back to scanning MongoDB for anything in 'running' state
        try:
            running_exp = db["experiments"].find_one({"status": "running"}, {"_id": 0})
            if running_exp:
                stopped_experiment_id = running_exp.get("experiment_id")
        except PyMongoError:
            pass
 
    if stopped_experiment_id:
        try:
            _upsert_experiment(db, stopped_experiment_id, {
                "status":   "stopped",
                "ended_at": now,
            })
            _log_event(db, stopped_experiment_id, "injection_stopped",
                       "Emergency stop triggered      all injections cancelled",
                       {"reset_results": results})
        except PyMongoError as e:
            print(f"[orchestrator] MongoDB update failed during emergency stop: {e}")
 
    return {
        "status":                  "emergency_stop_complete",
        "stopped_experiment_id":   stopped_experiment_id,
        "timestamp":               now.isoformat(),
        "reset_results":           results,
        "note": (
            "All injection reset endpoints were called. "
            "Check reset_results for individual outcomes."
        ),
    }
 
 
@app.get("/health")
def health():
    # check both Redis and MongoDB are reachable and if they arent make sure you ran that ip table fix script first ok
    mongo_ok = redis_ok = False
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        client[MONGO_DB].command("ping")
        client.close()
        mongo_ok = True
    except Exception:
        pass
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                        decode_responses=True, socket_connect_timeout=1)
        r.ping()
        r.close()
        redis_ok = True
    except Exception:
        pass
 
    return {
        "status":    "ok",
        "service":   "experiment_orchestrator",
        "mongo":     "connected" if mongo_ok  else "unreachable",
        "redis":     "connected" if redis_ok  else "unreachable",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
