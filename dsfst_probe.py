#!/usr/bin/env python3
"""Inspect local D.S.F.S.T databases and call its loopback APIs."""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parent
API_PORTS = range(8000, 8011)


def as_json(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def print_json(value):
    print(json.dumps(value, indent=2, default=as_json))


def local_api_path(path):
    parts = urlsplit(path)
    if not path.startswith("/") or path.startswith("//") or parts.scheme or parts.netloc or parts.fragment:
        raise ValueError("API path must begin with one / and contain no host or fragment")
    return path


def api_request(method, port, path, payload=None, timeout=5):
    url = f"http://127.0.0.1:{port}{local_api_path(path)}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    # A configured HTTP proxy must never receive local API requests.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        status = error.code
        body = error.read()
    except (URLError, TimeoutError, OSError) as error:
        return {"ok": False, "status": None, "error": str(error), "url": url}
    try:
        content = json.loads(body) if body else None
    except (ValueError, UnicodeDecodeError):
        content = body.decode("utf-8", errors="replace")
    return {"ok": 200 <= status < 300, "status": status, "url": url, "data": content}


def load_settings():
    try:
        from dotenv import dotenv_values
    except ImportError as error:
        raise RuntimeError("Install project dependencies with bash install_dsfst.sh") from error
    path = ROOT / ".env"
    if not path.is_file():
        raise RuntimeError(f"Missing {path}; run bash install_dsfst.sh inside the VM")
    return dotenv_values(path)


def safe_error(error, settings):
    message = f"{type(error).__name__}: {error}"
    uri = settings.get("MONGO_URI")
    if uri:
        message = message.replace(uri, "[redacted MongoDB URI]")
    for key in ("MONGO_PASSWORD", "INFLUXDB_TOKEN", "REDIS_PASSWORD", "INFLUX_PASSWORD"):
        secret = settings.get(key)
        if secret:
            message = message.replace(secret, "[redacted]")
    return message


def mongo_info(settings, limit):
    from pymongo import MongoClient

    uri = settings.get("MONGO_URI")
    if not uri:
        raise ValueError("MONGO_URI is missing from .env")
    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        client.admin.command("ping")
        database = client[settings.get("MONGO_DB_NAME") or "dsfst"]
        collections = {
            name: database[name].count_documents({})
            for name in sorted(database.list_collection_names())
        }
        recent = list(
            database["experiments"]
            .find({}, {"_id": 0, "experiment_id": 1, "name": 1, "status": 1, "created_at": 1})
            .sort("created_at", -1)
            .limit(limit)
        )
        return {"ok": True, "database": database.name, "collections": collections, "recent_experiments": recent}


def influx_info(settings, minutes):
    from influxdb_client import InfluxDBClient

    url = settings.get("INFLUXDB_URL")
    token = settings.get("INFLUXDB_TOKEN")
    org = settings.get("INFLUXDB_ORG") or "dsfst-org"
    bucket = settings.get("INFLUXDB_BUCKET") or "dsfst-bucket"
    if not url or not token:
        raise ValueError("INFLUXDB_URL or INFLUXDB_TOKEN is missing from .env")
    with InfluxDBClient(url=url, token=token, org=org, timeout=5000) as client:
        if not client.ping():
            raise RuntimeError("InfluxDB did not answer ping")
        if client.buckets_api().find_bucket_by_name(bucket) is None:
            raise RuntimeError(f"InfluxDB bucket {bucket!r} does not exist")
        flux = f"from(bucket: {json.dumps(bucket)}) |> range(start: -{minutes}m) |> last()"
        latest = {}
        for table in client.query_api().query(flux, org=org):
            for record in table.records:
                name = f"{record.get_measurement()}.{record.get_field()}"
                candidate = {"value": record.get_value(), "time": record.get_time()}
                if name not in latest or candidate["time"] > latest[name]["time"]:
                    latest[name] = candidate
        return {"ok": True, "bucket": bucket, "window_minutes": minutes, "latest_fields": latest}


def redis_info(settings):
    import redis

    with redis.Redis(
        host=settings.get("REDIS_HOST") or "127.0.0.1",
        port=int(settings.get("REDIS_PORT") or 6379),
        db=int(settings.get("REDIS_DB") or 0),
        username=settings.get("REDIS_USERNAME"),
        password=settings.get("REDIS_PASSWORD"),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    ) as client:
        client.ping()
        return {
            "ok": True,
            "state": client.get("dsft:state") or "idle",
            "active_experiment_id": client.get("dsft:active_experiment"),
        }


def database_report(limit, minutes):
    settings = load_settings()
    report = {}
    for name, action in (
        ("mongodb", lambda: mongo_info(settings, limit)),
        ("influxdb", lambda: influx_info(settings, minutes)),
        ("redis", lambda: redis_info(settings)),
    ):
        try:
            report[name] = action()
        except Exception as error:
            report[name] = {"ok": False, "error": safe_error(error, settings)}
    return report


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="GET the monitor, metrics, and orchestrator status")
    db = commands.add_parser("db", help="Read MongoDB, InfluxDB, and Redis summaries from local .env")
    db.add_argument("--limit", type=int, default=5, help="Recent MongoDB experiment count, 0-20")
    db.add_argument("--minutes", type=int, default=15, help="InfluxDB lookback window, 1-1440 minutes")
    api = commands.add_parser("api", help="Send an explicit GET or POST to a local D.S.F.S.T API")
    api.add_argument("method", choices=("GET", "POST"))
    api.add_argument("port", type=int, choices=API_PORTS)
    api.add_argument("path", help="Path such as /state or /experiments?limit=5")
    data = api.add_mutually_exclusive_group()
    data.add_argument("--data", help="JSON request body")
    data.add_argument("--json-file", type=Path, help="Read the JSON request body from a file")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            report = {
                "monitor": api_request("GET", 8000, "/status"),
                "metrics": api_request("GET", 8008, "/health"),
                "orchestrator": api_request("GET", 8009, "/state"),
            }
        elif args.command == "db":
            if not 0 <= args.limit <= 20 or not 1 <= args.minutes <= 1440:
                raise ValueError("--limit must be 0-20 and --minutes must be 1-1440")
            report = database_report(args.limit, args.minutes)
        else:
            if args.method == "GET" and (args.data is not None or args.json_file is not None):
                raise ValueError("GET cannot have a JSON request body")
            body = args.json_file.read_text(encoding="utf-8") if args.json_file else args.data
            payload = json.loads(body) if body is not None else None
            report = api_request(args.method, args.port, args.path, payload)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print_json(report)
    results = report.values() if args.command != "api" else (report,)
    return 0 if all(item.get("ok") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
