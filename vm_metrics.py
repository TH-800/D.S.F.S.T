"""Metrics scoped to registered VMs; remote readings stay in that VM's InfluxDB."""
from typing import Literal, Optional
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException, Query
from vm_registry import vm_request

FIELDS = {"cpu": ["cpu_usage_percent"],
          "memory": ["memory_used_mb", "memory_percent"],
          "network": ["latency_ms", "packet_loss_percent", "throughput_kbps"]}
Measurement = Literal["cpu", "memory", "network"]


def read_latest(registry, vm_id, read_local):
    vm = registry.get(vm_id or "local")
    data = read_local() if vm["is_local"] else vm_request(vm, 8008, "/metrics/latest")
    if not isinstance(data, dict) or not all(key in data for key in FIELDS):
        raise HTTPException(502, "VM metrics response is incomplete")
    return {**data, "vm_id": vm["vm_id"], "vm_name": vm["name"]}


def local_history(get_influx, org, bucket, measurement, minutes):
    influx = get_influx()
    if not influx:
        raise HTTPException(503, "InfluxDB is not configured")
    import json
    flux = f'''from(bucket: {json.dumps(bucket)})
      |> range(start: -{minutes}m)
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => {" or ".join(f'r._field == "{f}"' for f in FIELDS[measurement])})
      |> sort(columns: ["_time"])'''
    try:
        series = {field: [] for field in FIELDS[measurement]}
        for table in influx.query_api().query(flux, org=org):
            for record in table.records:
                series[record.get_field()].append(
                    {"timestamp": record.get_time().isoformat(), "value": record.get_value()})
        for points in series.values():
            points.sort(key=lambda point: point["timestamp"])
    except Exception as error:
        raise HTTPException(503, "InfluxDB metrics query unavailable") from error
    return {"measurement": measurement, "minutes": minutes, "series": series}


def build_metrics_router(registry, read_local, read_history):
    router = APIRouter(tags=["VM metrics"])

    @router.get("/metrics/latest")
    def latest(vm_id: Optional[str] = None):
        return read_latest(registry, vm_id, read_local)

    @router.get("/vms/{vm_id}/metrics/latest")
    def vm_latest(vm_id: str):
        return read_latest(registry, vm_id, read_local)

    def history_for(vm_id, measurement, minutes):
        vm = registry.get(vm_id or "local")
        if vm["is_local"]:
            result = read_history(measurement, minutes)
        else:
            query = urlencode({"measurement": measurement, "minutes": minutes})
            result = vm_request(vm, 8008, "/metrics/history?" + query)
        return {**result, "vm_id": vm["vm_id"], "vm_name": vm["name"]}

    @router.get("/metrics/history")
    def history(measurement: Measurement = "cpu",
                minutes: int = Query(default=15, ge=1, le=1440),
                vm_id: Optional[str] = None):
        return history_for(vm_id, measurement, minutes)

    @router.get("/vms/{vm_id}/metrics/history")
    def vm_history(vm_id: str, measurement: Measurement = "cpu",
                   minutes: int = Query(default=15, ge=1, le=1440)):
        return history_for(vm_id, measurement, minutes)

    return router
