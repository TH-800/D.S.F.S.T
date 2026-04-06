# metrics_writer.py
# Background service that polls the D.S.F.S.T monitoring and injection scripts
# every 5 seconds and persists the data to InfluxDB (metrics) and MongoDB (experiment state).
#
# What it writes:
#   InfluxDB   cpu, memory, network measurements every 5 seconds
#   MongoDB    experiment documents (created/updated on state changes)
#   MongoDB    log entries whenever state changes or injections start/stop
#
# Setup
#   pip install pymongo influxdb-client python-dotenv requests
#
# Run (in its own terminal, alongside the other services):
#   python metrics_writer.py
#
# It will keep running until you Ctrl+C it.
# All the monitoring services (ports 8000-8003) should already be running via RunAll.py. if not
# what are you doing

import time
import uuid
import requests
import os
import sys
from datetime import datetime, timezone


from dotenv import load_dotenv # reads key pairs from the .env file so we can have influx working and connected
from pathlib import Path #file system interaction 

from pymongo import MongoClient # used for connection mongo and python data dumping
from pymongo.errors import PyMongoError
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

def _normalise_type(t: str) -> str:
    """Map ExperimentMonitor internal type names to consistent frontend-friendly names."""
    return {
        "cpu_stress":      "cpu",
        "memory_stress":   "memory",
        "network_latency": "latency",
    }.get(t, t)


 # Config
 # UPDATE THE .ENV FILE ON YOUR SYSTEM AS THE .ENV FILE WILL BE DIFFERENT DURING SETUP
#YOU NEED TO HAVE YOUR TOKEN MADE FIRST THEN UPDATE THE .ENV FILE OR MAKE A NEW ONE OK DOKI

# find .env relative to this script so it works regardless of where uvicorn is launched
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=True)
load_dotenv(override=False)

# how often to poll the monitoring scripts and write metrics (seconds)
POLL_INTERVAL_SECONDS = 5
# IT SPAMS THE CONSOLE OUTPUT BUT WHO CARES

# base URLs for each monitoring script
CPU_URL     = "http://127.0.0.1:8002/cpu"
MEMORY_URL  = "http://127.0.0.1:8003/memory"
NETWORK_URL = "http://127.0.0.1:8001/network"
STATUS_URL       = "http://127.0.0.1:8000/status"   # ExperimentMonitor btw
ORCHESTRATOR_URL = "http://127.0.0.1:8009"            # ExperimentOrchestrator

# MongoDB config
# if anything here breaks its prob because of ipv6 on linux 22.02 or ip routing tables being broken
# so go find and read the fix i made in the text file 

MONGO_URI    = os.getenv("MONGO_URI",     "mongodb://127.0.0.1:27017/")
MONGO_DB     = os.getenv("MONGO_DB_NAME", "dsfst")

# InfluxDB config
INFLUX_URL    = os.getenv("INFLUXDB_URL",    "http://127.0.0.1:8086")
INFLUX_TOKEN  = os.getenv("INFLUXDB_TOKEN",  "")
INFLUX_ORG    = os.getenv("INFLUXDB_ORG",    "dsfst-org")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "dsfst-bucket")

 # DB connections (opened once, reused every poll cycle)
 
def connect_mongo():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")  # confirm connection is alive
        db = client[MONGO_DB]
        print(f"[MongoDB] Connected to {MONGO_URI} / {MONGO_DB}")
        return db
    except PyMongoError as e:
        print(f"[MongoDB] Connection failed: {e}")
        return None


def connect_influx():
    if not INFLUX_TOKEN:
        print("[InfluxDB] No token found in .env — metrics will NOT be written to InfluxDB.")
        print("[InfluxDB] Complete the InfluxDB first-time setup at http://localhost:8086 and add INFLUXDB_TOKEN to your .env file.")
        return None
    try:
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        client.ping()
        print(f"[InfluxDB] Connected to {INFLUX_URL}")
        return client
    except Exception as e:
        print(f"[InfluxDB] Connection failed: {e}")
        return None

 # Fetch helpers with each returning a dictionary(i asusme dict means that here or im dumb) or None on failure
 
def fetch_json(url: str, timeout: int = 4) -> dict | None:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        # service is offline this is expected when scripts aren't running SO GO RUN EM RunAll.py
        return None
    except Exception as e:
        print(f"[fetch] {url} error: {e}")
        return None

 # InfluxDB write helpers
 
def write_cpu_metric(write_api, cpu_data: dict):
    """Write a single CPU reading to InfluxDB."""
    container_id = cpu_data.get("container_id", "unknown")
    cpu_percent  = cpu_data.get("cpu_usage_percent", 0.0)

    point = (
        Point("cpu")
        .tag("container_id", container_id)
        .field("cpu_usage_percent", float(cpu_percent))
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)


def write_memory_metric(write_api, mem_data: dict):
    """Write a single memory reading to InfluxDB."""
    container_id  = mem_data.get("container_id", "unknown")
    memory_mb     = mem_data.get("memory_used_mb", 0.0)
    memory_pct    = mem_data.get("memory_percent", 0.0)

    point = (
        Point("memory")
        .tag("container_id", container_id)
        .field("memory_used_mb",  float(memory_mb))
        .field("memory_percent",  float(memory_pct))
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)


def write_network_metric(write_api, net_data: dict):
    """Write a single network reading to InfluxDB."""
    container_id   = net_data.get("container_id", "unknown")
    latency_ms     = net_data.get("latency_ms", 0.0)
    packet_loss    = net_data.get("packet_loss_percent", 0.0)
    throughput     = net_data.get("throughput_kbps", 0.0)

    point = (
        Point("network")
        .tag("container_id", container_id)
        .field("latency_ms",          float(latency_ms))
        .field("packet_loss_percent", float(packet_loss))
        .field("throughput_kbps",     float(throughput))
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

 # MongoDB experiment + log helpers
 
def log_event(db, experiment_id: str, event_type: str, message: str, details: dict = None):
    """Insert a single log entry into the logs collection."""
    entry = {
        "log_id":        str(uuid.uuid4()),
        "experiment_id": experiment_id,
        "event_type":    event_type,   # info | warning | error | injection_started | injection_stopped
        "message":       message,
        "timestamp":     datetime.now(timezone.utc),
        "details":       details or {},
    }
    try:
        db["logs"].insert_one(entry)
    except PyMongoError as e:
        print(f"[MongoDB] log_event failed: {e}")


def upsert_experiment(db, experiment_id: str, fields: dict):
    """Create or update an experiment document."""
    try:
        db["experiments"].update_one(
            {"experiment_id": experiment_id},
            {"$set": fields},
            upsert=True,
        )
    except PyMongoError as e:
        print(f"[MongoDB] upsert_experiment failed: {e}")

 # State tracking in which  we compare last_state to current_state each cycle and cause the terminal to be filled up with garbage
# to detect transitions and only write to MongoDB on changes
 
class StateTracker:
    def __init__(self):
        self.last_state: str = "idle"
        # experiment_id of the currently running experiment
        # we generate one when we first detect "running" and keep it until were idle
        self.active_experiment_id: str | None = None
        # snapshot of active_experiments from the last status poll so we can
        # detect when a new injection type appears mid run
        self.last_active_experiments: list = []

    def handle_state(self, db, current_state: str, active_experiments: list):
        """
        Called every poll cycle with the current machine state.
        Writes MongoDB documents and logs based on state transitions.
        """
        now = datetime.now(timezone.utc)

        # idle to running: a new experiment just started
        if self.last_state != "running" and current_state == "running":
            # Check if the orchestrator already created an experiment for this run
            # so we don't create a duplicate "cpu experiment" / "memory experiment" record
            orchestrator_exp_id = None
            try:
                orch = fetch_json(f"{ORCHESTRATOR_URL}/state", timeout=3)
                if orch and orch.get("state") == "running":
                    orchestrator_exp_id = orch.get("active_experiment_id")
            except Exception:
                pass

            if orchestrator_exp_id:
                # orchestrator owns this experiment adopt its ID, don't create a new one
                self.active_experiment_id = orchestrator_exp_id
                print(f"[state] running     adopted orchestrator experiment {orchestrator_exp_id}")
                # still log the detection event
                log_event(db, orchestrator_exp_id, "info",
                          "metrics_writer detected injection start via ExperimentMonitor",
                          {"active_experiments": active_experiments})
            else:
                # no orchestrator experiment found create our own tracking record
                exp_id = str(uuid.uuid4())
                self.active_experiment_id = exp_id

                types = [_normalise_type(e.get("type", "unknown")) for e in active_experiments]
                failure_type = "+".join(sorted(set(types))) if types else "unknown"

                params = {}
                for exp in active_experiments:
                    p = exp.get("params", {})
                    norm = _normalise_type(exp.get("type", "unknown"))
                    if norm == "cpu":
                        params["cpu_workers"] = exp.get("intensity")
                    elif norm == "memory":
                        params["memory_config"] = exp.get("intensity")
                    elif norm == "latency":
                        params["delay"] = p.get("delay")
                    elif norm == "packet_loss":
                        params["loss_percent"] = p.get("loss_percent")

                upsert_experiment(db, exp_id, {
                    "experiment_id": exp_id,
                    "name":          f"{failure_type} experiment",
                    "failure_type":  failure_type,
                    "target_container": active_experiments[0].get("source", "unknown") if active_experiments else "unknown",
                    "parameters":    params,
                    "status":        "running",
                    "created_at":    now,
                    "started_at":    now,
                    "ended_at":      None,
                })
                log_event(db, exp_id, "injection_started",
                          f"Experiment started: {failure_type}",
                          {"active_experiments": active_experiments})
                print(f"[state] running     experiment {exp_id} created ({failure_type})")

        # running to complete or idle experiment finished or (stress-ng timed out)
        elif self.last_state == "running" and current_state in ("complete", "idle", "stopping"):
            if self.active_experiment_id:
                upsert_experiment(db, self.active_experiment_id, {
                    "status":   "completed",
                    "ended_at": now,
                })
                log_event(db, self.active_experiment_id, "injection_stopped",
                          f"Experiment ended, new state: {current_state}")
                print(f"[state] stopped     experiment {self.active_experiment_id} marked complete")

                # Tell the orchestrator to clean up Redis state so the dashboard
                # shows "idle" instead of staying stuck on "running"
                _exp_id = self.active_experiment_id
                self.active_experiment_id = None
                try:
                    import requests as _req
                    _req.post(f"{ORCHESTRATOR_URL}/emergency-stop", timeout=8)
                    print(f"[state] orchestrator Redis cleared via emergency-stop")
                except Exception:
                    pass
            else:
                self.active_experiment_id = None

        # still running but a new injection type appeared 
        elif current_state == "running" and self.active_experiment_id:
            new_ids = {e.get("experiment_id") for e in active_experiments}
            old_ids = {e.get("experiment_id") for e in self.last_active_experiments}
            added = new_ids - old_ids
            if added:
                log_event(db, self.active_experiment_id, "info",
                          f"Additional injection detected: {added}",
                          {"active_experiments": active_experiments})

        self.last_state = current_state
        self.last_active_experiments = active_experiments

 # Main poll loop
 
def run():
    print("=" * 60)
    print("  D.S.F.S.T Metrics Writer")
    print(f"  Polling every {POLL_INTERVAL_SECONDS}s  |  Ctrl+C to stop")
    print("=" * 60)

    db         = connect_mongo()
    influx     = connect_influx()
    write_api  = influx.write_api(write_options=SYNCHRONOUS) if influx else None
    tracker    = StateTracker()

    if db is None:
        print("[ERROR] Cannot connect to MongoDB. Is docker-compose up and running?")
        sys.exit(1)

    # Startup cleanup and mark any experiments that are stuck as "running" from a
    # previous session as "stopped" nad If the service restarted, those injections
    # are definitely no longer active.
    try:
        stale = list(db["experiments"].find({"status": "running"}, {"experiment_id": 1}))
        if stale:
            ids = [e["experiment_id"] for e in stale]
            db["experiments"].update_many(
                {"status": "running"},
                {"$set": {"status": "stopped", "ended_at": datetime.now(timezone.utc)}}
            )
            print(f"[startup] Marked {len(ids)} stale 'running' experiment(s) as stopped: {ids}")
    except Exception as e:
        print(f"[startup] Stale cleanup failed (non-critical): {e}")

    # Startup check if the orchestrator already has an active experiment in Redis
    # so we don't create a duplicate when we detect the "running" state
    try:
        orch_state = fetch_json(f"{ORCHESTRATOR_URL}/state", timeout=3)
        if orch_state and orch_state.get("state") == "running":
            existing_id = orch_state.get("active_experiment_id")
            if existing_id:
                tracker.active_experiment_id = existing_id
                tracker.last_state = "running"
                print(f"[startup] Adopted existing orchestrator experiment: {existing_id}")
    except Exception:
        pass  # orchestrator might not be running yet

    cycle = 0
    while True:
        cycle += 1
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

        #  poll all monitoring scripts   
        cpu_data = fetch_json(CPU_URL)
        mem_data = fetch_json(MEMORY_URL)
        # network uses a longer timeout — BaseNetworkInfo.py pings 8.8.8.8 x5 which takes ~5s
        net_data = fetch_json(NETWORK_URL, timeout=15)
        status   = fetch_json(STATUS_URL)

        #  write to InfluxDB   
        if write_api:
            try:
                if cpu_data:
                    write_cpu_metric(write_api, cpu_data)
                if mem_data:
                    write_memory_metric(write_api, mem_data)
                if net_data:
                    write_network_metric(write_api, net_data)
            except Exception as e:
                print(f"[InfluxDB] Write error: {e}")

        #  track experiment state in MongoDB   
        if status:
            current_state       = status.get("state", "idle")
            active_experiments  = status.get("active_experiments", [])
            tracker.handle_state(db, current_state, active_experiments)

        #  console heartbeat (every 10 cycles = 50s)   
        if cycle % 10 == 0:
            cpu_pct = cpu_data.get("cpu_usage_percent", "?") if cpu_data else "offline"
            mem_pct = mem_data.get("memory_percent",    "?") if mem_data else "offline"
            lat_ms  = net_data.get("latency_ms",        "?") if net_data else "offline"
            state   = status.get("state", "?") if status else "monitor offline"
            print(f"[{ts}] cycle={cycle}  cpu={cpu_pct}%  mem={mem_pct}%  lat={lat_ms}ms  state={state}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n[metrics_writer] Stopped.")
