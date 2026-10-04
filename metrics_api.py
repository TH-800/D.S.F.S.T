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
#   GET /experiments
#   GET /experiments/{id}
#   GET /experiments/{id}/logs
#   GET /experiments/{id}/metrics
#   GET /metrics/history
#   GET /metrics/latest
#   GET /experiments/{id}/export
#   GET /experiments/{id}/report
#   GET /reports/summary
#   GET /health


import csv
import io
import json
import os

from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from influxdb_client import InfluxDBClient
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError


# Find .env relative to this script so it works
# regardless of where uvicorn is launched.
_ENV_FILE = Path(__file__).resolve().parent / ".env"

load_dotenv(
    dotenv_path=_ENV_FILE,
    override=True
)

load_dotenv(
    override=False
)


# Config

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://127.0.0.1:27017/"
)

MONGO_DB = os.getenv(
    "MONGO_DB_NAME",
    "dsfst"
)

INFLUX_URL = os.getenv(
    "INFLUXDB_URL",
    "http://127.0.0.1:8086"
)

INFLUX_TOKEN = os.getenv(
    "INFLUXDB_TOKEN",
    ""
)

INFLUX_ORG = os.getenv(
    "INFLUXDB_ORG",
    "dsfst-org"
)

INFLUX_BUCKET = os.getenv(
    "INFLUXDB_BUCKET",
    "dsfst-bucket"
)


# App + connections

app = FastAPI(
    title="D.S.F.S.T Metrics API",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_mongo_client = None
_influx_client = None


def get_db():

    global _mongo_client

    if _mongo_client is None:

        _mongo_client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=10000
        )

    return _mongo_client[MONGO_DB]


def get_influx():

    global _influx_client

    if _influx_client is None and INFLUX_TOKEN:

        _influx_client = InfluxDBClient(
            url=INFLUX_URL,
            token=INFLUX_TOKEN,
            org=INFLUX_ORG
        )

    return _influx_client


# Serialisation helper for MongoDB documents

def serialise(doc: dict) -> dict:

    """Convert a MongoDB document to a JSON dict."""

    clean = {}

    for k, v in doc.items():

        if k == "_id":

            continue

        if isinstance(v, datetime):

            clean[k] = v.isoformat()

        elif isinstance(v, dict):

            clean[k] = serialise(v)

        elif isinstance(v, list):

            clean[k] = [
                serialise(i)
                if isinstance(i, dict)
                else i
                for i in v
            ]

        else:

            clean[k] = v

    return clean


# /experiments

@app.get("/experiments")
def list_experiments(

    limit: int = Query(
        default=50,
        ge=1,
        le=200
    ),

    status: Optional[str] = Query(
        default=None
    ),

):

    """
    Return a list of experiments, newest first.

    Optionally filter by status.
    """

    db = get_db()

    query = {}

    if status:

        query["status"] = status

    try:

        docs = (

            db["experiments"]

            .find(
                query,
                {"_id": 0}
            )

            .sort(
                "created_at",
                DESCENDING
            )

            .limit(limit)

        )

        return [
            serialise(d)
            for d in docs
        ]

    except PyMongoError as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: str
):

    """Return a single experiment document."""

    db = get_db()

    try:

        doc = db[
            "experiments"
        ].find_one(

            {
                "experiment_id": experiment_id
            },

            {
                "_id": 0
            }

        )

    except PyMongoError as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    if not doc:

        raise HTTPException(
            status_code=404,
            detail="Experiment not found"
        )

    return serialise(doc)


# /experiments/{id}/logs

@app.get("/experiments/{experiment_id}/logs")
def get_experiment_logs(

    experiment_id: str,

    limit: int = Query(
        default=200,
        ge=1,
        le=1000
    ),

    event_type: Optional[str] = Query(
        default=None
    ),

):

    """
    Return log entries for a single experiment,
    oldest first.

    Optionally filter by event_type.
    """

    db = get_db()

    query: dict = {
        "experiment_id": experiment_id
    }

    if event_type:

        query["event_type"] = event_type

    try:

        docs = (

            db["logs"]

            .find(
                query,
                {"_id": 0}
            )

            .sort(
                "timestamp",
                1
            )

            .limit(limit)

        )

        return [
            serialise(d)
            for d in docs
        ]

    except PyMongoError as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/logs/recent")
def get_recent_logs(

    limit: int = Query(
        default=100,
        ge=1,
        le=500
    )

):

    """
    Return the most recent log entries across all experiments.
    """

    db = get_db()

    try:

        docs = (

            db["logs"]

            .find(
                {},
                {"_id": 0}
            )

            .sort(
                "timestamp",
                DESCENDING
            )

            .limit(limit)

        )

        return list(
            reversed(
                [
                    serialise(d)
                    for d in docs
                ]
            )
        )

    except PyMongoError as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# /experiments/{id}/metrics - InfluxDB time-series data

@app.get("/experiments/{experiment_id}/metrics")
def get_experiment_metrics(

    experiment_id: str,

    measurement: str = Query(
        default="cpu",
        enum=[
            "cpu",
            "memory",
            "network"
        ]
    ),

    minutes: int = Query(
        default=60,
        ge=1,
        le=1440
    ),

):

    """
    Return InfluxDB time-series data.

    measurement: cpu | memory | network
    minutes: how far back to look.
    """

    influx = get_influx()

    if not influx:

        raise HTTPException(

            status_code=503,

            detail=(
                "InfluxDB is not configured. "
                "Add INFLUXDB_TOKEN to your .env file."
            )

        )


    field_map = {

        "cpu": [
            "cpu_usage_percent"
        ],

        "memory": [
            "memory_used_mb",
            "memory_percent"
        ],

        "network": [
            "latency_ms",
            "packet_loss_percent",
            "throughput_kbps"
        ],

    }

    fields = field_map[
        measurement
    ]


    flux = f"""
from(bucket: "{INFLUX_BUCKET}")

  |> range(start: -{minutes}m)

  |> filter(
      fn: (r) =>
          r._measurement == "{measurement}"
  )

  |> filter(
      fn: (r) =>
          {" or ".join(
              f'r._field == "{f}"'
              for f in fields
          )}
  )

  |> sort(columns: ["_time"])
"""


    try:

        query_api = influx.query_api()

        tables = query_api.query(
            flux,
            org=INFLUX_ORG
        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=(
                f"InfluxDB query failed: {e}"
            )

        )


    series: dict[str, dict] = {}


    for table in tables:

        for record in table.records:

            field = record.get_field()

            time = (
                record
                .get_time()
                .isoformat()
            )

            value = record.get_value()


            if field not in series:

                series[field] = {

                    "label": field,

                    "labels": [],

                    "data": []

                }


            series[field][
                "labels"
            ].append(
                time
            )


            series[field][
                "data"
            ].append(
                value
            )


    if not series:

        return {

            "labels": [],

            "datasets": []

        }


    first_field = list(
        series.keys()
    )[0]


    labels = series[
        first_field
    ]["labels"]


    datasets = [

        {

            "label": f,

            "data": series[f][
                "data"
            ]

        }

        for f in series

    ]


    return {

        "labels": labels,

        "datasets": datasets

    }


# /metrics/history - historical CPU and memory data

@app.get("/metrics/history")
def get_metrics_history(

    minutes: int = Query(
        default=60,
        ge=1,
        le=1440
    ),

):

    """
    Return historical CPU and memory utilization
    from InfluxDB.
    """

    influx = get_influx()


    if not influx:

        raise HTTPException(

            status_code=503,

            detail=(
                "InfluxDB is not configured. "
                "Add INFLUXDB_TOKEN to your .env file."
            )

        )


    if minutes <= 60:

        window = "10s"

    elif minutes <= 360:

        window = "1m"

    else:

        window = "5m"


    flux = f"""
from(bucket: "{INFLUX_BUCKET}")

  |> range(start: -{minutes}m)

  |> filter(
      fn: (r) =>
          (
              r._measurement == "cpu" and
              r._field == "cpu_usage_percent"
          )
          or
          (
              r._measurement == "memory" and
              r._field == "memory_percent"
          )
  )

  |> aggregateWindow(
      every: {window},
      fn: mean,
      createEmpty: false
  )

  |> keep(
      columns: [
          "_time",
          "_measurement",
          "_value"
      ]
  )

  |> sort(
      columns: ["_time"]
  )
"""


    try:

        query_api = influx.query_api()

        tables = query_api.query(
            flux,
            org=INFLUX_ORG
        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=(
                f"InfluxDB query failed: {e}"
            )

        )


    points = {}


    for table in tables:

        for record in table.records:

            timestamp = (
                record
                .get_time()
                .isoformat()
            )

            measurement = (
                record
                .get_measurement()
            )

            value = (
                record
                .get_value()
            )


            if timestamp not in points:

                points[timestamp] = {

                    "time": timestamp

                }


            if value is None:

                continue


            if measurement == "cpu":

                points[
                    timestamp
                ]["cpu"] = round(
                    float(value),
                    2
                )


            elif measurement == "memory":

                points[
                    timestamp
                ]["memory"] = round(
                    float(value),
                    2
                )


    history = sorted(

        points.values(),

        key=lambda item: item[
            "time"
        ]

    )


    return {

        "range_minutes": minutes,

        "points": history

    }


# /metrics/latest

@app.get("/metrics/latest")
def get_latest_metrics():

    """
    Return the single most recent reading
    for CPU, memory, and network from InfluxDB.
    """

    influx = get_influx()


    if not influx:

        return {

            "error":
                "InfluxDB not configured",

            "cpu":
                None,

            "memory":
                None,

            "network":
                None

        }


    results = {}


    for measurement, fields in {

        "cpu": [
            "cpu_usage_percent"
        ],

        "memory": [
            "memory_used_mb",
            "memory_percent"
        ],

        "network": [
            "latency_ms",
            "packet_loss_percent",
            "throughput_kbps"
        ],

    }.items():


        flux = f"""
from(bucket: "{INFLUX_BUCKET}")

  |> range(start: -10m)

  |> filter(
      fn: (r) =>
          r._measurement == "{measurement}"
  )

  |> filter(
      fn: (r) =>
          {" or ".join(
              f'r._field == "{f}"'
              for f in fields
          )}
  )

  |> last()
"""


        try:

            query_api = influx.query_api()

            tables = query_api.query(
                flux,
                org=INFLUX_ORG
            )


            entry = {}


            for table in tables:

                for record in table.records:

                    entry[
                        record.get_field()
                    ] = (
                        record
                        .get_value()
                    )


                    entry[
                        "timestamp"
                    ] = (

                        record
                        .get_time()
                        .isoformat()

                    )


            results[
                measurement
            ] = (
                entry
                or None
            )


        except Exception:

            results[
                measurement
            ] = None


    return results


# /experiments/{id}/report

@app.get("/experiments/{experiment_id}/report")
def get_experiment_report(

    experiment_id: str

):

    """
    Returns aggregated before/during/after
    stats for one experiment.
    """

    influx = get_influx()

    db = get_db()


    try:

        exp = db[
            "experiments"
        ].find_one(

            {
                "experiment_id":
                    experiment_id
            },

            {
                "_id": 0
            }

        )

    except PyMongoError as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


    if not exp:

        raise HTTPException(

            status_code=404,

            detail=(
                "Experiment not found"
            )

        )


    started_at = exp.get(
        "started_at"
    )

    ended_at = exp.get(
        "ended_at"
    )


    if (
        not influx
        or not started_at
        or not ended_at
    ):

        return {

            "id":
                experiment_id,

            "experimentName":
                exp.get("name"),

            "type":
                exp.get(
                    "failure_type"
                ),

            "startedAt":
                started_at.isoformat()
                if isinstance(
                    started_at,
                    datetime
                )
                else started_at,

            "completedAt":
                ended_at.isoformat()
                if isinstance(
                    ended_at,
                    datetime
                )
                else ended_at,

            "baseline":
                None,

            "peak":
                None,

            "avgDuringTest":
                None,

            "note":
                (
                    "InfluxDB not configured "
                    "or experiment still running."
                ),

        }


    def flux_agg(

        start: datetime,

        stop: datetime,

        fn: str,

        field: str,

        measurement: str

    ) -> float | None:


        start_s = start.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )


        stop_s = stop.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )


        flux = f"""
from(bucket: "{INFLUX_BUCKET}")

  |> range(
      start: {start_s},
      stop: {stop_s}
  )

  |> filter(
      fn: (r) =>
          r._measurement == "{measurement}"
          and
          r._field == "{field}"
  )

  |> {fn}()
"""


        try:

            tables = (
                influx
                .query_api()
                .query(
                    flux,
                    org=INFLUX_ORG
                )
            )


            for table in tables:

                for record in table.records:

                    v = (
                        record
                        .get_value()
                    )


                    return (
                        round(v, 2)
                        if v is not None
                        else None
                    )


        except Exception:

            pass


        return None


    baseline_start = (
        started_at
        - timedelta(
            minutes=2
        )
    )


    baseline_stop = (
        started_at
    )


    baseline = {

        "cpuPercent":

            flux_agg(

                baseline_start,

                baseline_stop,

                "mean",

                "cpu_usage_percent",

                "cpu"

            ),


        "memoryPercent":

            flux_agg(

                baseline_start,

                baseline_stop,

                "mean",

                "memory_percent",

                "memory"

            ),


        "latencyMs":

            flux_agg(

                baseline_start,

                baseline_stop,

                "mean",

                "latency_ms",

                "network"

            ),

    }


    peak = {

        "cpuPercent":

            flux_agg(

                started_at,

                ended_at,

                "max",

                "cpu_usage_percent",

                "cpu"

            ),


        "memoryPercent":

            flux_agg(

                started_at,

                ended_at,

                "max",

                "memory_percent",

                "memory"

            ),


        "latencyMs":

            flux_agg(

                started_at,

                ended_at,

                "max",

                "latency_ms",

                "network"

            ),

    }


    avg_during = {

        "cpuPercent":

            flux_agg(

                started_at,

                ended_at,

                "mean",

                "cpu_usage_percent",

                "cpu"

            ),


        "memoryPercent":

            flux_agg(

                started_at,

                ended_at,

                "mean",

                "memory_percent",

                "memory"

            ),


        "latencyMs":

            flux_agg(

                started_at,

                ended_at,

                "mean",

                "latency_ms",

                "network"

            ),

    }


    return {

        "id":
            experiment_id,

        "experimentName":
            exp.get("name"),

        "type":
            exp.get(
                "failure_type"
            ),

        "parameters":
            exp.get(
                "parameters",
                {}
            ),

        "startedAt":
            started_at.isoformat()
            if isinstance(
                started_at,
                datetime
            )
            else started_at,

        "completedAt":
            ended_at.isoformat()
            if isinstance(
                ended_at,
                datetime
            )
            else ended_at,

        "baseline":
            baseline,

        "peak":
            peak,

        "avgDuringTest":
            avg_during,

    }


# /reports/summary

@app.get("/reports/summary")
def get_reports_summary(

    limit: int = Query(
        default=20,
        ge=1,
        le=100
    )

):

    """
    Return report information for
    completed experiments.
    """

    db = get_db()


    try:

        docs = (

            db["experiments"]

            .find(

                {
                    "status":
                        "completed"
                },

                {
                    "_id": 0
                }

            )

            .sort(
                "ended_at",
                DESCENDING
            )

            .limit(limit)

        )


        experiments = list(
            docs
        )


    except PyMongoError as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


    summaries = []


    for exp in experiments:


        summaries.append({

            "id":

                exp.get(
                    "experiment_id"
                ),

            "experimentName":

                exp.get(
                    "name"
                ),

            "type":

                exp.get(
                    "failure_type"
                ),

            "parameters":

                exp.get(
                    "parameters",
                    {}
                ),

            "startedAt":

                exp[
                    "started_at"
                ].isoformat()

                if isinstance(
                    exp.get(
                        "started_at"
                    ),
                    datetime
                )

                else exp.get(
                    "started_at"
                ),

            "completedAt":

                exp[
                    "ended_at"
                ].isoformat()

                if isinstance(
                    exp.get(
                        "ended_at"
                    ),
                    datetime
                )

                else exp.get(
                    "ended_at"
                ),

            "status":

                exp.get(
                    "status"
                ),

        })


    return summaries


# /experiments/{id}/export

@app.get("/experiments/{experiment_id}/export")
def export_experiment(

    experiment_id: str,

    format: str = Query(
        default="json",
        enum=[
            "json",
            "csv"
        ]
    ),

):

    """
    Download experiment metadata and logs
    as JSON or CSV.
    """

    db = get_db()


    try:

        exp = db[
            "experiments"
        ].find_one(

            {
                "experiment_id":
                    experiment_id
            },

            {
                "_id": 0
            }

        )


    except PyMongoError as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


    if not exp:

        raise HTTPException(

            status_code=404,

            detail=(
                "Experiment not found"
            )

        )


    try:

        logs = list(

            db["logs"]

            .find(

                {
                    "experiment_id":
                        experiment_id
                },

                {
                    "_id": 0
                }

            )

            .sort(
                "timestamp",
                1
            )

        )


    except PyMongoError as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


    exp_clean = serialise(
        exp
    )


    logs_clean = [

        serialise(l)

        for l in logs

    ]


    filename = (
        f"dsft_export_"
        f"{experiment_id[:8]}"
    )


    if format == "json":


        payload = json.dumps(

            {

                "experiment":
                    exp_clean,

                "logs":
                    logs_clean

            },

            indent=2

        )


        return StreamingResponse(

            io.StringIO(
                payload
            ),

            media_type=(
                "application/json"
            ),

            headers={

                "Content-Disposition":

                    (
                        f'attachment; '
                        f'filename="'
                        f'{filename}.json"'
                    )

            }

        )


    output = io.StringIO()


    writer = csv.writer(
        output
    )


    writer.writerow([
        "# EXPERIMENT"
    ])


    writer.writerow([

        "experiment_id",

        "name",

        "failure_type",

        "target_container",

        "status",

        "started_at",

        "ended_at"

    ])


    writer.writerow([

        exp_clean.get(
            "experiment_id"
        ),

        exp_clean.get(
            "name"
        ),

        exp_clean.get(
            "failure_type"
        ),

        exp_clean.get(
            "target_container"
        ),

        exp_clean.get(
            "status"
        ),

        exp_clean.get(
            "started_at"
        ),

        exp_clean.get(
            "ended_at"
        ),

    ])


    writer.writerow([])


    writer.writerow([
        "# PARAMETERS"
    ])


    for k, v in (

        exp_clean.get(
            "parameters"
        )

        or {}

    ).items():


        writer.writerow([

            k,

            v

        ])


    writer.writerow([])


    writer.writerow([
        "# LOGS"
    ])


    writer.writerow([

        "log_id",

        "timestamp",

        "event_type",

        "message",

        "details"

    ])


    for log in logs_clean:


        writer.writerow([

            log.get(
                "log_id"
            ),

            log.get(
                "timestamp"
            ),

            log.get(
                "event_type"
            ),

            log.get(
                "message"
            ),

            json.dumps(

                log.get(
                    "details",
                    {}
                )

            ),

        ])


    output.seek(0)


    return StreamingResponse(

        output,

        media_type="text/csv",

        headers={

            "Content-Disposition":

                (
                    f'attachment; '
                    f'filename="'
                    f'{filename}.csv"'
                )

        }

    )


# /health

@app.get("/health")
def health():

    return {

        "status":
            "ok",

        "service":
            "metrics_api",

        "timestamp":

            datetime.now(
                timezone.utc
            ).isoformat(),

    }