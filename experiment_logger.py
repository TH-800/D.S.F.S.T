# experiment_logger.py
# Helper module for logging injection events to MongoDB.
#
# This can be imported by other scripts OR run directly to log a single event
# from the command line (useful for manual testing).
#
# Usage as a module:
#   from experiment_logger import ExperimentLogger
#   logger = ExperimentLogger()
#   exp_id = logger.start_experiment("cpu_stress", {"cpu_percent": 50, "duration_seconds": 60})
#   logger.log_event(exp_id, "info", "Stress is running")
#   logger.stop_experiment(exp_id)
#
# Usage from the command line:
#   python experiment_logger.py start  cpu_stress   '{"cpu_percent": 50}'
#   python experiment_logger.py stop   <experiment_id>
#   python experiment_logger.py list
#   python experiment_logger.py logs   <experiment_id>
#
# Setup:
#   pip install pymongo python-dotenv

import uuid
import json
import sys
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError

# find .env relative to this script so it works regardless of where uvicorn is launched
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE)

#UPDATE THE ENV FILE BECAUSE IT WILL DIFFER FROM VMWARE TO VMWARE 
# AND CHANGE THE LOCALHOST AS NEEDED IF NEEDED
#KEEP ALL THE NAMES THE SAME except for the tokenID
MONGO_URI = os.getenv("MONGO_URI",     "mongodb://localhost:27017/")
MONGO_DB  = os.getenv("MONGO_DB_NAME", "dsfst")


class ExperimentLogger:
    """
    MongoDB experiment and log writes for D.S.F.S.T.
    One instance can be kept open for the lifetime of the metrics_writer service.
    """

    def __init__(self):
        self._client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        self._db     = self._client[MONGO_DB]
        self._exps   = self._db["experiments"]
        self._logs   = self._db["logs"]

      
    # Experiment lifecycle
      

    def start_experiment(
        self,
        failure_type: str,
        parameters: dict,
        target_container: str = "LinuxMachineHere",
        name: str = None,
    ) -> str:
        """
        Creates a new experiment document with status 'running'.
        Returns the new experiment_id string.
        """
        experiment_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        doc = {
            "experiment_id":    experiment_id,
            "name":             name or f"{failure_type} — {now.strftime('%Y-%m-%d %H:%M')}",
            "failure_type":     failure_type,
            "target_container": target_container,
            "parameters":       parameters,
            "status":           "running",
            "created_at":       now,
            "started_at":       now,
            "ended_at":         None,
        }

        try:
            self._exps.insert_one(doc)
        except PyMongoError as e:
            print(f"[ExperimentLogger] start_experiment failed: {e}")

        # write the first log entry
        self.log_event(
            experiment_id,
            "injection_started",
            f"Injection started: {failure_type}",
            details={"parameters": parameters, "target_container": target_container},
        )

        return experiment_id

    def stop_experiment(self, experiment_id: str, status: str = "completed"):
        """
        Marks an existing experiment as completed (or failed/stopped).
        Writes a final log entry.
        """
        now = datetime.now(timezone.utc)
        try:
            self._exps.update_one(
                {"experiment_id": experiment_id},
                {"$set": {"status": status, "ended_at": now}},
            )
        except PyMongoError as e:
            print(f"[ExperimentLogger] stop_experiment failed: {e}")

        self.log_event(
            experiment_id,
            "injection_stopped",
            f"Injection stopped. Final status: {status}",
        )

    def update_experiment(self, experiment_id: str, fields: dict):
        """Partial update of any experiment fields."""
        try:
            self._exps.update_one(
                {"experiment_id": experiment_id},
                {"$set": fields},
            )
        except PyMongoError as e:
            print(f"[ExperimentLogger] update_experiment failed: {e}")

      
    # Log entries
      

    def log_event(
        self,
        experiment_id: str,
        event_type: str,
        message: str,
        details: dict = None,
    ):
        """
        Append a log entry to the logs collection.

        event_type should be one of:
            injection_started | injection_stopped | metric_collected | info | warning | error
        """
        entry = {
            "log_id":        str(uuid.uuid4()),
            "experiment_id": experiment_id,
            "event_type":    event_type,
            "message":       message,
            "timestamp":     datetime.now(timezone.utc),
            "details":       details or {},
        }
        try:
            self._logs.insert_one(entry)
        except PyMongoError as e:
            print(f"[ExperimentLogger] log_event failed: {e}")

    def log_metric_snapshot(
        self,
        experiment_id: str,
        cpu_percent: float,
        memory_percent: float,
        latency_ms: float,
    ):
        """
        Convenience wrapper to log a lightweight metric snapshot to MongoDB.
        (InfluxDB gets the full time-series; this gives the logs page something to show.)
        """
        self.log_event(
            experiment_id,
            "metric_collected",
            f"cpu={cpu_percent}%  mem={memory_percent}%  lat={latency_ms}ms",
            details={
                "cpu_percent":    cpu_percent,
                "memory_percent": memory_percent,
                "latency_ms":     latency_ms,
            },
        )

      
    # Read helpers (for CLI use / quick debugging)
      

    def list_experiments(self, limit: int = 20) -> list:
        """Return the most recent experiments, newest first."""
        cursor = (
            self._exps
            .find({}, {"_id": 0})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        return list(cursor)

    def get_logs(self, experiment_id: str, limit: int = 100) -> list:
        """Return log entries for a specific experiment, oldest first."""
        cursor = (
            self._logs
            .find({"experiment_id": experiment_id}, {"_id": 0})
            .sort("timestamp", 1)
            .limit(limit)
        )
        return list(cursor)

    def close(self):
        self._client.close()


  
# CLI interface
  

def _print_json(data):
    def default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Cannot serialize {type(obj)}")
    print(json.dumps(data, indent=2, default=default))



# error checking was vibe coded because i wanted a fancy debug output for error fixing 
if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python experiment_logger.py start  <failure_type> '<params_json>'")
        print("  python experiment_logger.py stop   <experiment_id>")
        print("  python experiment_logger.py list")
        print("  python experiment_logger.py logs   <experiment_id>")
        sys.exit(0)

    logger = ExperimentLogger()
    cmd = args[0]

    if cmd == "start":
        if len(args) < 2:
            print("Usage: python experiment_logger.py start <failure_type> '<params_json>'")
            sys.exit(1)
        failure_type = args[1]
        params = json.loads(args[2]) if len(args) > 2 else {}
        exp_id = logger.start_experiment(failure_type, params)
        print(f"Started experiment: {exp_id}")

    elif cmd == "stop":
        if len(args) < 2:
            print("Usage: python experiment_logger.py stop <experiment_id>")
            sys.exit(1)
        logger.stop_experiment(args[1])
        print(f"Stopped experiment: {args[1]}")

    elif cmd == "list":
        experiments = logger.list_experiments()
        _print_json(experiments)

    elif cmd == "logs":
        if len(args) < 2:
            print("Usage: python experiment_logger.py logs <experiment_id>")
            sys.exit(1)
        logs = logger.get_logs(args[1])
        _print_json(logs)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

    logger.close()