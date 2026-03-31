# metrics_api.py
# FastAPI retrieval service — reads from MongoDB and InfluxDB and exposes
# endpoints the D.S.F.S.T frontend can call to display real persisted data.
#
# Runs on port 8008.
#
# Setup:
#   pip install fastapi uvicorn pymongo influxdb-client python-dotenv
#
# Run:
#   python -m uvicorn metrics_api:app --host 127.0.0.1 --port 8008 --reload
#
# Endpoints (all read-only):
#
#   GET /experiments                      list all experiments, newest first
#   GET /experiments/{id}                 single experiment document
#   GET /experiments/{id}/logs            log entries for one experiment
#   GET /experiments/{id}/metrics         InfluxDB time-series for one experiment
#   GET /experiments/{id}/export          download JSON or CSV of all experiment data
#   GET /experiments/{id}/report          aggregated before/during/after stats (Reports page)
#   GET /metrics/latest                   most recent CPU / memory / network readings
#   GET /reports/summary                  summary stats across ALL completed experiments
 
import csv
import io
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional
 
from dotenv import load_dotenv
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from influxdb_client import InfluxDBClient
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError
 
# find .env relative to this script so it works regardless of where uvicorn is launched
# try the script's own directory first, then fall back to cwd
# and if it cant find it that means you didnt make one or you didnt copy it 
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=True)
load_dotenv(override=False)  # fallback: picks up .env in cwd if above didn't load it
 
  
# Config
  
 
MONGO_URI     = os.getenv("MONGO_URI",       "mongodb://127.0.0.1:27017/")
MONGO_DB      = os.getenv("MONGO_DB_NAME",   "dsfst")
INFLUX_URL    = os.getenv("INFLUXDB_URL",    "http://127.0.0.1:8086")
INFLUX_TOKEN  = os.getenv("INFLUXDB_TOKEN",  "")
INFLUX_ORG    = os.getenv("INFLUXDB_ORG",    "dsfst-org")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "dsfst-bucket")
 
  
# App + connections
  
 
app = FastAPI(title="D.S.F.S.T Metrics API", version="1.0.0")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
_mongo_client  = None
_influx_client = None
 
 
def get_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    return _mongo_client[MONGO_DB]
 
 
def get_influx():
    global _influx_client
    if _influx_client is None and INFLUX_TOKEN:
        _influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    return _influx_client
 
 
  
# Serialisation helper MongoDB documents contain datetime objects
# which are not JSON-serialisable by default so just screw me then as i have to convert it all
  # if it were  not for google and stackoverflow and whatever work ai stole id have never gotten any of this done
  
 
def serialise(doc: dict) -> dict:
    """Convert a MongoDB document to a JSON dict."""
    clean = {}
    for k, v in doc.items():
        if k == "_id":
            continue  # drop the internal MongoDB ObjectId
        if isinstance(v, datetime):
            clean[k] = v.isoformat()
        elif isinstance(v, dict):
            clean[k] = serialise(v)
        elif isinstance(v, list):
            clean[k] = [serialise(i) if isinstance(i, dict) else i for i in v]
        else:
            clean[k] = v
    return clean
 
 
  
# /experiments
  
 # abit of vibe coding was done here as i aint a mongoDB expert 
 # if it was mySQL then id be fine 
@app.get("/experiments")
def list_experiments(
    limit:  int = Query(default=50,  ge=1, le=200),
    status: Optional[str] = Query(default=None),
):
    """
    Return a list of experiments, newest first.
    Optionally filter by status (running | completed | failed).
 
    Response shape matches the Experiment interface in frontend/store.tsx.
    """
    db = get_db()
    query = {}
    if status:
        query["status"] = status
 
    try:
        docs = (
            db["experiments"]
            .find(query, {"_id": 0})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        return [serialise(d) for d in docs]
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str):
    """Return a single experiment document."""
    db = get_db()
    try:
        doc = db["experiments"].find_one(
            {"experiment_id": experiment_id}, {"_id": 0}
        )
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    if not doc:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return serialise(doc)
 
 
  
# /experiments/{id}/logs
  
 
@app.get("/experiments/{experiment_id}/logs")
def get_experiment_logs(
    experiment_id: str,
    limit:      int = Query(default=200, ge=1, le=1000),
    event_type: Optional[str] = Query(default=None),
):
    """
    Return log entries for a single experiment, oldest first.
    Optionally filter by event_type (injection_started | injection_stopped | info | warning | error | metric_collected).
 
    Response shape matches the LogEntry interface in frontend/store.tsx.
    """
    db = get_db()
    query: dict = {"experiment_id": experiment_id}
    if event_type:
        query["event_type"] = event_type
 
    try:
        docs = (
            db["logs"]
            .find(query, {"_id": 0})
            .sort("timestamp", 1)
            .limit(limit)
        )
        return [serialise(d) for d in docs]
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/logs/recent")
def get_recent_logs(limit: int = Query(default=100, ge=1, le=500)):
    """
    Return the most recent log entries across ALL experiments.
    Used by the Logs page to populate the log viewer on load.
    """
    db = get_db()
    try:
        docs = (
            db["logs"]
            .find({}, {"_id": 0})
            .sort("timestamp", DESCENDING)
            .limit(limit)
        )
        # return in chronological order so the UI can append newest at the bottom
        return list(reversed([serialise(d) for d in docs]))
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
  
# /experiments/{id}/metrics  and nfluxDB timeseries data
  
 
@app.get("/experiments/{experiment_id}/metrics")
def get_experiment_metrics(
    experiment_id: str,
    measurement: str = Query(default="cpu", enum=["cpu", "memory", "network"]),
    minutes: int = Query(default=60, ge=1, le=1440),
):
    """
    Return InfluxDB time-series data for one experiment.
 
    measurement: cpu | memory | network
    minutes:     how far back to look (default 60 minutes)
 
    Returns a Chart.js-compatible format: which should look like this i think
    {
      "labels": ["2026-03-26T14:00:00", ...],
      "datasets": [
        { "label": "cpu_usage_percent", "data": [42.3, 44.1, ...] },
        ...
      ]
    }
    """
    influx = get_influx()
    if not influx:
        raise HTTPException(
            status_code=503,
            detail="InfluxDB is not configured. Add INFLUXDB_TOKEN to your .env file.",
        )
 
    field_map = {
        "cpu":     ["cpu_usage_percent"],
        "memory":  ["memory_used_mb", "memory_percent"],
        "network": ["latency_ms", "packet_loss_percent", "throughput_kbps"],
    }
    fields = field_map[measurement]
 
    # build a Flux query that pulls the requested measurement for the time window
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => {" or ".join(f'r._field == "{f}"' for f in fields)})
  |> sort(columns: ["_time"])
"""
 
    try:
        query_api = influx.query_api()
        tables    = query_api.query(flux, org=INFLUX_ORG)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"InfluxDB query failed: {e}")
 
    # group results by field name
    series: dict[str, dict] = {}
    for table in tables:
        for record in table.records:
            field  = record.get_field()
            time   = record.get_time().isoformat()
            value  = record.get_value()
 
            if field not in series:
                series[field] = {"label": field, "labels": [], "data": []}
            series[field]["labels"].append(time)
            series[field]["data"].append(value)
 
    if not series:
        return {"labels": [], "datasets": []}
 
    # all fields share the same timestamps so we use the first one for the label axis in the column 
    first_field = list(series.keys())[0]
    labels      = series[first_field]["labels"]
    datasets    = [{"label": f, "data": series[f]["data"]} for f in series]
 
    return {"labels": labels, "datasets": datasets}
 
 
@app.get("/metrics/latest")
def get_latest_metrics():
    """
    Return the single most recent reading for CPU, memory, and network from InfluxDB.
    Used by the Dashboard to seed the initial display before the 5-second poll kicks in.
    """
    influx = get_influx()
    if not influx:
        return {"error": "InfluxDB not configured", "cpu": None, "memory": None, "network": None}
 
    results = {}
    for measurement, fields in {
        "cpu":     ["cpu_usage_percent"],
        "memory":  ["memory_used_mb", "memory_percent"],
        "network": ["latency_ms", "packet_loss_percent", "throughput_kbps"],
    }.items():
        flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -10m)
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => {" or ".join(f'r._field == "{f}"' for f in fields)})
  |> last()
"""
        try:
            query_api = influx.query_api()
            tables    = query_api.query(flux, org=INFLUX_ORG)
            entry = {}
            for table in tables:
                for record in table.records:
                    entry[record.get_field()] = record.get_value()
                    entry["timestamp"]        = record.get_time().isoformat()
            results[measurement] = entry or None
        except Exception:
            results[measurement] = None
 
    return results
 
 
  
# /experiments/{id}/report  stats for the Reports page
  
 
@app.get("/experiments/{experiment_id}/report")
def get_experiment_report(experiment_id: str):
    """
    Returns aggregated before/during/after stats for one experiment.
    The shape matches the Report interface in frontend/store.tsx so the
    Reports page can display it directly.
 
    {
      "id": "...",
      "experimentName": "...",
      "type": "cpu_stress",
      "startedAt": "...",
      "completedAt": "...",
      "baseline":  { "cpuPercent": 12.1, "memoryPercent": 45.2, "latencyMs": 18.3 },
      "peak":      { "cpuPercent": 61.0, "memoryPercent": 47.0, "latencyMs": 22.1 },
      "avgDuringTest": { "cpuPercent": 53.2, "memoryPercent": 46.1, "latencyMs": 20.4 }
    }
    """
    influx = get_influx()
    db     = get_db()
 
    # get the experiment document first
    try:
        exp = db["experiments"].find_one({"experiment_id": experiment_id}, {"_id": 0})
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
 
    started_at   = exp.get("started_at")
    ended_at     = exp.get("ended_at")
 
    if not influx or not started_at or not ended_at:
        # return what we have without InfluxDB aggregation
        return {
            "id":             experiment_id,
            "experimentName": exp.get("name"),
            "type":           exp.get("failure_type"),
            "startedAt":      started_at.isoformat() if isinstance(started_at, datetime) else started_at,
            "completedAt":    ended_at.isoformat()   if isinstance(ended_at,   datetime) else ended_at,
            "baseline":       None,
            "peak":           None,
            "avgDuringTest":  None,
            "note":           "InfluxDB not configured or experiment still running.",
        }
 
    def flux_agg(start: datetime, stop: datetime, fn: str, field: str, measurement: str) -> float | None:
        """Run a single Flux aggregation (mean or max) over a time window."""
        start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        stop_s  = stop.strftime( "%Y-%m-%dT%H:%M:%SZ")
        flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {start_s}, stop: {stop_s})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}")
  |> {fn}()
"""
        try:
            tables = influx.query_api().query(flux, org=INFLUX_ORG)
            for table in tables:
                for record in table.records:
                    v = record.get_value()
                    return round(v, 2) if v is not None else None
        except Exception:
            pass
        return None
 
    # baseline = 2 minutes before the experiment started
    baseline_start = started_at - timedelta(minutes=2)
    baseline_stop  = started_at
 
    baseline = {
        "cpuPercent":    flux_agg(baseline_start, baseline_stop, "mean", "cpu_usage_percent",    "cpu"),
        "memoryPercent": flux_agg(baseline_start, baseline_stop, "mean", "memory_percent",       "memory"),
        "latencyMs":     flux_agg(baseline_start, baseline_stop, "mean", "latency_ms",           "network"),
    }
 
    peak = {
        "cpuPercent":    flux_agg(started_at, ended_at, "max",  "cpu_usage_percent",    "cpu"),
        "memoryPercent": flux_agg(started_at, ended_at, "max",  "memory_percent",       "memory"),
        "latencyMs":     flux_agg(started_at, ended_at, "max",  "latency_ms",           "network"),
    }
 
    avg_during = {
        "cpuPercent":    flux_agg(started_at, ended_at, "mean", "cpu_usage_percent",    "cpu"),
        "memoryPercent": flux_agg(started_at, ended_at, "mean", "memory_percent",       "memory"),
        "latencyMs":     flux_agg(started_at, ended_at, "mean", "latency_ms",           "network"),
    }
 
    return {
        "id":             experiment_id,
        "experimentName": exp.get("name"),
        "type":           exp.get("failure_type"),
        "parameters":     exp.get("parameters", {}),
        "startedAt":      started_at.isoformat() if isinstance(started_at, datetime) else started_at,
        "completedAt":    ended_at.isoformat()   if isinstance(ended_at,   datetime) else ended_at,
        "baseline":       baseline,
        "peak":           peak,
        "avgDuringTest":  avg_during,
    }
 
 
  
# /reports/summary stats across all completed experiments
  
 
@app.get("/reports/summary")
def get_reports_summary(limit: int = Query(default=20, ge=1, le=100)):
    """
    Return aggregated report cards for all completed experiments.
    Calls /experiments/{id}/report for each one.
    Used by the Reports page to populate the report list on load.
    """
    db = get_db()
    try:
        docs = (
            db["experiments"]
            .find({"status": "completed"}, {"_id": 0})
            .sort("ended_at", DESCENDING)
            .limit(limit)
        )
        experiments = list(docs)
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    # build a  summary for each one (no InfluxDB here 
    # the frontend can call /experiments/{id}/report per card
    summaries = []
    for exp in experiments:
        summaries.append({
            "id":             exp.get("experiment_id"),
            "experimentName": exp.get("name"),
            "type":           exp.get("failure_type"),
            "parameters":     exp.get("parameters", {}),
            "startedAt":      exp["started_at"].isoformat() if isinstance(exp.get("started_at"), datetime) else exp.get("started_at"),
            "completedAt":    exp["ended_at"].isoformat()   if isinstance(exp.get("ended_at"),   datetime) else exp.get("ended_at"),
            "status":         exp.get("status"),
        })
    return summaries
 
 
  
# /experiments/{id}/export download JSON or CSV
  
 
@app.get("/experiments/{experiment_id}/export")
def export_experiment(
    experiment_id: str,
    format: str = Query(default="json", enum=["json", "csv"]),
):
    """
    Download a full export of one experiment: metadata + logs.
    format: json (default) | csv and im not changing it 
    """
    db = get_db()
 
    try:
        exp = db["experiments"].find_one({"experiment_id": experiment_id}, {"_id": 0})
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
 
    try:
        logs = list(
            db["logs"]
            .find({"experiment_id": experiment_id}, {"_id": 0})
            .sort("timestamp", 1)
        )
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    exp_clean  = serialise(exp)
    logs_clean = [serialise(l) for l in logs]
 
    filename = f"dsft_export_{experiment_id[:8]}"
 
    # JSON export   
    if format == "json":
        payload = json.dumps(
            {"experiment": exp_clean, "logs": logs_clean},
            indent=2,
        )
        return StreamingResponse(
            io.StringIO(payload),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
        )
 
    #  CSV export   
    output = io.StringIO()
    writer = csv.writer(output)
 
    # experiment header rows
    writer.writerow(["# EXPERIMENT"])
    writer.writerow(["experiment_id", "name", "failure_type", "target_container",
                     "status", "started_at", "ended_at"])
    writer.writerow([
        exp_clean.get("experiment_id"),
        exp_clean.get("name"),
        exp_clean.get("failure_type"),
        exp_clean.get("target_container"),
        exp_clean.get("status"),
        exp_clean.get("started_at"),
        exp_clean.get("ended_at"),
    ])
 
    # parameters block as key=value rows
    writer.writerow([])
    writer.writerow(["# PARAMETERS"])
    for k, v in (exp_clean.get("parameters") or {}).items():
        writer.writerow([k, v])
 
    # log entries
    writer.writerow([])
    writer.writerow(["# LOGS"])
    writer.writerow(["log_id", "timestamp", "event_type", "message", "details"])
    for log in logs_clean:
        writer.writerow([
            log.get("log_id"),
            log.get("timestamp"),
            log.get("event_type"),
            log.get("message"),
            json.dumps(log.get("details", {})),
        ])
 
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )
 
 
  
# /health
  
 
@app.get("/health")
def health():
    return {
        "status":    "ok",
        "service":   "metrics_api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }