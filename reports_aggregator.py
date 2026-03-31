# reports_aggregator.py
# Task 4.5 — Reporting queries that aggregate data from MongoDB
# to calculate statistics for completed experiments.
#
# Runs on port 8010.
#
# Setup:
#   pip install fastapi uvicorn pymongo python-dotenv
#
# Run:
#   python -m uvicorn reports_aggregator:app --host 127.0.0.1 --port 8010 --reload
#
# Endpoints:
#
#   GET /reports/aggregate              overall stats across all completed experiments
#   GET /reports/by-type                per failure_type breakdown (count, avg duration, avg metrics)
#   GET /reports/failure-counts         how many experiments of each type ran and how many failed
#   GET /reports/timeline               completed experiments ordered by date for a timeline view
#   GET /reports/experiment/{id}/stats  detailed stats for one experiment (pulled from InfluxDB too)
 
import os
from datetime import datetime, timezone
from typing import Optional
 
from dotenv import load_dotenv
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError
 
# find .env relative to this script so it works regardless of where uvicorn is launched
# try the script's own directory first, then fall back to cwd
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=True)
load_dotenv(override=False)  # fallback: picks up .env in cwd if above didn't load it
 
MONGO_URI = os.getenv("MONGO_URI",     "mongodb://127.0.0.1:27017/")
MONGO_DB  = os.getenv("MONGO_DB_NAME", "dsfst")
 
app = FastAPI(title="D.S.F.S.T Reports Aggregator", version="1.0.0")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
 
def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    return client[MONGO_DB]
 
 
def _serialise_dates(doc: dict) -> dict:
    """Recursively convert datetime objects to ISO strings."""
    out = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = _serialise_dates(v)
        elif isinstance(v, list):
            out[k] = [_serialise_dates(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out
 
 
 # GET /reports/aggregate
  
@app.get("/reports/aggregate")
def get_aggregate_stats():
    """
    Overall statistics across ALL completed experiments.
 
    Returns:
    {
      "total_experiments":     int,
      "completed_experiments": int,
      "failed_experiments":    int,
      "average_duration_seconds": float,
      "longest_experiment_seconds": float,
      "shortest_experiment_seconds": float,
      "most_common_type":      str,
      "type_counts":           { "cpu": 3, "latency": 2, ... },
      "failure_rate_percent":  float,
      "generated_at":          str
    }
    """
    db = get_db()
 
    try:
        #   total counts by status  
        status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_results = list(db["experiments"].aggregate(status_pipeline))
        status_map = {r["_id"]: r["count"] for r in status_results}
 
        total       = sum(status_map.values())
        completed   = status_map.get("completed", 0)
        failed      = status_map.get("failed", 0)
        stopped     = status_map.get("stopped", 0)
 
        #   duration stats for completed experiments  
        duration_pipeline = [
            {
                "$match": {
                    "status":     "completed",
                    "started_at": {"$ne": None},
                    "ended_at":   {"$ne": None},
                }
            },
            {
                "$addFields": {
                    "duration_seconds": {
                        "$divide": [
                            {"$subtract": ["$ended_at", "$started_at"]},
                            1000  # MongoDB returns milliseconds
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id":      None,
                    "avg_dur":  {"$avg":  "$duration_seconds"},
                    "max_dur":  {"$max":  "$duration_seconds"},
                    "min_dur":  {"$min":  "$duration_seconds"},
                }
            }
        ]
        dur_results = list(db["experiments"].aggregate(duration_pipeline))
        dur = dur_results[0] if dur_results else {}
 
        #   type breakdown  
        type_pipeline = [
            {"$group": {"_id": "$failure_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        type_results  = list(db["experiments"].aggregate(type_pipeline))
        type_counts   = {r["_id"]: r["count"] for r in type_results if r["_id"]}
        most_common   = type_results[0]["_id"] if type_results else None
 
        failure_rate = round(
            ((failed + stopped) / total * 100) if total > 0 else 0.0, 2
        )
 
        return {
            "total_experiments":           total,
            "completed_experiments":       completed,
            "failed_experiments":          failed,
            "stopped_experiments":         stopped,
            "average_duration_seconds":    round(dur.get("avg_dur") or 0, 2),
            "longest_experiment_seconds":  round(dur.get("max_dur") or 0, 2),
            "shortest_experiment_seconds": round(dur.get("min_dur") or 0, 2),
            "most_common_type":            most_common,
            "type_counts":                 type_counts,
            "failure_rate_percent":        failure_rate,
            "generated_at":                datetime.now(timezone.utc).isoformat(),
        }
 
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
 # GET /reports/by-type
  
@app.get("/reports/by-type")
def get_stats_by_type():
    """
    Per failure_type breakdown.
    Calculates: count, avg duration, success rate for each type.
 
    Returns a list of objects, one per type:
    [
      {
        "failure_type":            "cpu",
        "total_runs":              5,
        "completed_runs":          4,
        "avg_duration_seconds":    45.2,
        "success_rate_percent":    80.0,
        "last_run_at":             "2026-03-26T..."
      },
      ...
    ]
    """
    db = get_db()
 
    try:
        pipeline = [
            # only include experiments that have actually run (not just 'created')
            {"$match": {"status": {"$in": ["completed", "failed", "stopped", "running"]}}},
            {
                "$addFields": {
                    "duration_seconds": {
                        "$cond": {
                            "if": {
                                "$and": [
                                    {"$ne": ["$started_at", None]},
                                    {"$ne": ["$ended_at",   None]},
                                ]
                            },
                            "then": {
                                "$divide": [
                                    {"$subtract": ["$ended_at", "$started_at"]},
                                    1000
                                ]
                            },
                            "else": None,
                        }
                    },
                    "is_completed": {
                        "$cond": [{"$eq": ["$status", "completed"]}, 1, 0]
                    }
                }
            },
            {
                "$group": {
                    "_id":          "$failure_type",
                    "total_runs":   {"$sum": 1},
                    "completed":    {"$sum": "$is_completed"},
                    "avg_duration": {"$avg": "$duration_seconds"},
                    "last_run_at":  {"$max": "$started_at"},
                }
            },
            {"$sort": {"total_runs": -1}},
        ]
 
        results = list(db["experiments"].aggregate(pipeline))
        output  = []
 
        for r in results:
            total   = r["total_runs"]
            success = r["completed"]
            output.append({
                "failure_type":         r["_id"] or "unknown",
                "total_runs":           total,
                "completed_runs":       success,
                "avg_duration_seconds": round(r["avg_duration"] or 0, 2),
                "success_rate_percent": round((success / total * 100) if total > 0 else 0, 2),
                "last_run_at":          r["last_run_at"].isoformat() if isinstance(r.get("last_run_at"), datetime) else r.get("last_run_at"),
            })
 
        return output
 
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
 # GET /reports/failure-counts
  
@app.get("/reports/failure-counts")
def get_failure_counts():
    """
    How many experiments of each type ran, succeeded, and failed.
    Used for the Reports page summary cards and bar charts.
 
    Returns:
    {
      "summary": {
        "total":     12,
        "completed": 9,
        "failed":    1,
        "stopped":   2
      },
      "by_type": [
        { "type": "cpu",      "total": 4, "completed": 3, "failed": 0, "stopped": 1 },
        { "type": "latency",  "total": 5, "completed": 5, "failed": 0, "stopped": 0 },
        ...
      ]
    }
    """
    db = get_db()
 
    try:
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "type":   "$failure_type",
                        "status": "$status",
                    },
                    "count": {"$sum": 1},
                }
            },
        ]
        results = list(db["experiments"].aggregate(pipeline))
 
        # rebuild into a nested dict: { type: { status: count } }
        by_type: dict[str, dict[str, int]] = {}
        totals  = {"total": 0, "completed": 0, "failed": 0, "stopped": 0}
 
        for r in results:
            t      = r["_id"].get("type")   or "unknown"
            status = r["_id"].get("status") or "unknown"
            count  = r["count"]
 
            if t not in by_type:
                by_type[t] = {"total": 0, "completed": 0, "failed": 0, "stopped": 0}
 
            by_type[t]["total"] += count
            if status in by_type[t]:
                by_type[t][status] += count
 
            totals["total"] += count
            if status in totals:
                totals[status] += count
 
        by_type_list = [
            {"type": t, **counts}
            for t, counts in sorted(by_type.items(), key=lambda x: -x[1]["total"])
        ]
 
        return {"summary": totals, "by_type": by_type_list}
 
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
 # GET /reports/timeline
  
@app.get("/reports/timeline")
def get_timeline(
    limit: int = Query(default=30, ge=1, le=200),
    failure_type: Optional[str] = Query(default=None),
):
    """
    Completed experiments in chronological order for a timeline view on the Reports page.
    Each entry includes the duration so the frontend can draw a Gantt-style bar.
 
    Returns a list ordered newest-first:
    [
      {
        "experiment_id": "...",
        "name":          "...",
        "failure_type":  "cpu",
        "status":        "completed",
        "started_at":    "2026-03-26T14:00:00",
        "ended_at":      "2026-03-26T14:01:00",
        "duration_seconds": 60
      },
      ...
    ]
    """
    db = get_db()
 
    match_filter: dict = {"status": {"$in": ["completed", "failed", "stopped"]}}
    if failure_type:
        match_filter["failure_type"] = failure_type
 
    try:
        pipeline = [
            {"$match": match_filter},
            {
                "$addFields": {
                    "duration_seconds": {
                        "$cond": {
                            "if": {
                                "$and": [
                                    {"$ne": ["$started_at", None]},
                                    {"$ne": ["$ended_at",   None]},
                                ]
                            },
                            "then": {
                                "$divide": [
                                    {"$subtract": ["$ended_at", "$started_at"]},
                                    1000
                                ]
                            },
                            "else": 0,
                        }
                    }
                }
            },
            {"$sort":  {"started_at": DESCENDING}},
            {"$limit": limit},
            {
                "$project": {
                    "_id":              0,
                    "experiment_id":    1,
                    "name":             1,
                    "failure_type":     1,
                    "status":           1,
                    "started_at":       1,
                    "ended_at":         1,
                    "duration_seconds": 1,
                    "parameters":       1,
                }
            }
        ]
 
        docs = list(db["experiments"].aggregate(pipeline))
        return [_serialise_dates(d) for d in docs]
 
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
 # GET /reports/experiment/{id}/stats
  
@app.get("/reports/experiment/{experiment_id}/stats")
def get_experiment_stats(experiment_id: str):
    """
    Detailed stats for one experiment — pulled entirely from MongoDB logs.
    Counts events by type, extracts metric snapshots from log entries,
    and calculates min/avg/max for CPU, memory, and latency.
 
    This is the MongoDB-only version of what metrics_api.py /experiments/{id}/report
    does with InfluxDB, so it works even without InfluxDB configured.
 
    Returns:
    {
      "experiment_id": "...",
      "name": "...",
      "failure_type": "...",
      "duration_seconds": 60,
      "log_summary": {
        "total_events":     15,
        "injection_started": 1,
        "injection_stopped": 1,
        "metric_collected":  12,
        "errors":            0,
        "info":              1
      },
      "metric_stats": {
        "cpu_percent":    { "min": 38.0, "avg": 52.1, "max": 61.0 },
        "memory_percent": { "min": 55.0, "avg": 57.3, "max": 62.0 },
        "latency_ms":     { "min": 18.0, "avg": 22.5, "max": 34.1 }
      }
    }
    """
    db = get_db()
 
    try:
        exp = db["experiments"].find_one({"experiment_id": experiment_id}, {"_id": 0})
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
 
    try:
        #   log event count breakdown  
        event_pipeline = [
            {"$match": {"experiment_id": experiment_id}},
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        ]
        event_results = list(db["logs"].aggregate(event_pipeline))
        event_counts  = {r["_id"]: r["count"] for r in event_results}
 
        #   metric snapshots stored in log details  
        # metrics_writer.py's log_metric_snapshot stores cpu_percent,
        # memory_percent, latency_ms inside the 'details' field of metric_collected logs
        metric_pipeline = [
            {
                "$match": {
                    "experiment_id": experiment_id,
                    "event_type":    "metric_collected",
                }
            },
            {
                "$group": {
                    "_id": None,
                    "cpu_min":  {"$min": "$details.cpu_percent"},
                    "cpu_avg":  {"$avg": "$details.cpu_percent"},
                    "cpu_max":  {"$max": "$details.cpu_percent"},
                    "mem_min":  {"$min": "$details.memory_percent"},
                    "mem_avg":  {"$avg": "$details.memory_percent"},
                    "mem_max":  {"$max": "$details.memory_percent"},
                    "lat_min":  {"$min": "$details.latency_ms"},
                    "lat_avg":  {"$avg": "$details.latency_ms"},
                    "lat_max":  {"$max": "$details.latency_ms"},
                    "count":    {"$sum": 1},
                }
            }
        ]
        metric_results = list(db["logs"].aggregate(metric_pipeline))
        m = metric_results[0] if metric_results else {}
 
        def _round(v):
            return round(v, 2) if v is not None else None
 
        metric_stats = {
            "cpu_percent": {
                "min": _round(m.get("cpu_min")),
                "avg": _round(m.get("cpu_avg")),
                "max": _round(m.get("cpu_max")),
            },
            "memory_percent": {
                "min": _round(m.get("mem_min")),
                "avg": _round(m.get("mem_avg")),
                "max": _round(m.get("mem_max")),
            },
            "latency_ms": {
                "min": _round(m.get("lat_min")),
                "avg": _round(m.get("lat_avg")),
                "max": _round(m.get("lat_max")),
            },
        }
 
        #   duration  
        started  = exp.get("started_at")
        ended    = exp.get("ended_at")
        duration = None
        if started and ended:
            duration = round((ended - started).total_seconds(), 2)
 
        return {
            "experiment_id": experiment_id,
            "name":          exp.get("name"),
            "failure_type":  exp.get("failure_type"),
            "status":        exp.get("status"),
            "started_at":    started.isoformat() if isinstance(started, datetime) else started,
            "ended_at":      ended.isoformat()   if isinstance(ended,   datetime) else ended,
            "duration_seconds": duration,
            "log_summary": {
                "total_events":       sum(event_counts.values()),
                "injection_started":  event_counts.get("injection_started", 0),
                "injection_stopped":  event_counts.get("injection_stopped", 0),
                "metric_collected":   event_counts.get("metric_collected",  0),
                "errors":             event_counts.get("error",              0),
                "info":               event_counts.get("info",               0),
            },
            "metric_stats": metric_stats,
        }
 
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
 # Health
  
@app.get("/health")
def health():
    mongo_ok = False
    try:
        get_db().command("ping")
        mongo_ok = True
    except Exception:
        pass
    return {
        "status":    "ok",
        "service":   "reports_aggregator",
        "mongo":     "connected" if mongo_ok else "unreachable",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }