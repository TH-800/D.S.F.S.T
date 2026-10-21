"""Check the installed stack through its browser gateway before setup succeeds."""
import argparse
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


class ReadinessError(RuntimeError):
    pass


def read_response(base_url, path):
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    # Local VM checks should not be sent through a workstation proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        return response.headers.get_content_type(), response.read().decode("utf-8")


def read_json(base_url, path):
    _, body = read_response(base_url, path)
    return json.loads(body)


def require(condition, message):
    if not condition:
        raise ReadinessError(message)


def valid_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def ensure_idle(base_url):
    state = read_json(base_url, "/api/8009/state")
    require(isinstance(state, dict) and state.get("state") in ("idle", "complete") and
            not state.get("active_experiment_id"),
            "Finish or stop the active experiment before setup.")
    try:
        batches = read_json(base_url, "/api/8009/experiment-batches?active_only=true&limit=50")
    except urllib.error.HTTPError as error:
        if error.code == 404:  # Older installations did not have batch routes.
            return
        raise
    require(isinstance(batches, list) and all(isinstance(batch, dict) for batch in batches),
            "Could not confirm the multi-VM batch state.")
    require(all(batch.get("status") in ("completed", "stopped", "failed") for batch in batches),
            "Finish or stop active multi-VM batches before setup.")


def check_ready(base_url):
    def fetch(path):
        try:
            return read_json(base_url, path)
        except (OSError, ValueError) as error:
            raise ReadinessError(f"{path}: {error}") from error

    content_type, page = read_response(base_url, "/")
    require(content_type == "text/html" and 'id="root"' in page,
            "The dashboard page is unavailable.")
    for port in range(8001, 8008):
        body = fetch(f"/api/{port}/")
        require(isinstance(body, dict) and bool(body), f"Backend {port} is unavailable.")
    for port, service in ((8000, "ExperimentMonitor"), (8008, "metrics_api"),
                          (8009, "experiment_orchestrator"), (8010, "reports_aggregator")):
        body = fetch(f"/api/{port}/health")
        require(isinstance(body, dict) and body.get("status") == "ok" and body.get("service") == service,
                f"Backend {port} did not confirm its health.")
        if port in (8009, 8010):
            require(body.get("mongo") == "connected", f"Backend {port} cannot reach MongoDB.")
        if port == 8009:
            require(body.get("redis") == "connected", "The orchestrator cannot reach Redis.")
    state = fetch("/api/8009/state")
    require(isinstance(state, dict) and state.get("state") in ("idle", "complete") and
            not state.get("active_experiment_id"), "The orchestrator is not idle.")
    vms = fetch("/api/8009/vms")
    require(isinstance(vms, list) and any(isinstance(vm, dict) and vm.get("vm_id") == "local" for vm in vms),
            "VM registration storage is unavailable.")
    readings = fetch("/api/8008/metrics/latest")
    require(isinstance(readings, dict) and readings.get("vm_id") == "local" and not readings.get("error"),
            "Local stored metrics are unavailable.")
    now = datetime.now(timezone.utc)
    for measurement, fields in {
        "cpu": ("cpu_usage_percent",),
        "memory": ("memory_used_mb", "memory_percent"),
        "network": ("latency_ms", "packet_loss_percent", "throughput_kbps"),
    }.items():
        sample = readings.get(measurement)
        require(isinstance(sample, dict), f"Waiting for stored {measurement} readings.")
        require(all(valid_number(sample.get(field)) for field in fields),
                f"Stored {measurement} readings are invalid.")
        try:
            timestamp = datetime.fromisoformat(sample["timestamp"].replace("Z", "+00:00"))
            age = (now - timestamp).total_seconds()
        except (KeyError, AttributeError, TypeError, ValueError) as error:
            raise ReadinessError(f"Stored {measurement} timestamp is invalid.") from error
        require(-10 <= age <= 60, f"Waiting for fresh stored {measurement} readings.")


def wait_until_ready(base_url, timeout=720, interval=3):
    deadline = time.monotonic() + timeout
    previous = None
    while True:
        try:
            check_ready(base_url)
            return
        except (ReadinessError, OSError, ValueError, TypeError) as error:
            reason = str(error)
            if time.monotonic() >= deadline:
                raise ReadinessError(f"Startup did not become ready: {reason} Check journalctl -u dsfst.service.") from error
            if reason != previous:
                print(f"Waiting for stack: {reason}", flush=True)
                previous = reason
            time.sleep(min(interval, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--timeout", type=float, default=720)
    parser.add_argument("--check-idle", action="store_true")
    arguments = parser.parse_args()
    if not math.isfinite(arguments.timeout) or arguments.timeout < 0:
        parser.error("timeout must be a finite nonnegative number")
    try:
        if arguments.check_idle:
            ensure_idle(arguments.base_url)
        else:
            wait_until_ready(arguments.base_url, arguments.timeout)
    except (ReadinessError, OSError, ValueError, TypeError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
