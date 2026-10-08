"""Persistent VM registration and bounded access to private VM gateways."""
import ipaddress
import os
import socket
import uuid
from urllib.parse import urlsplit
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.errors import DuplicateKeyError, PyMongoError
import requests

PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
ACTIVE_BATCH_STATES = ["starting", "running", "partial_failure", "stopping"]


def normalise_vm_url(value):
    try:
        parsed = urlsplit(value.strip())
        ip = ipaddress.IPv4Address(parsed.hostname or "")
        valid = (parsed.scheme == "http" and parsed.port == 3000 and
                 parsed.username is None and parsed.password is None and
                 parsed.path in ("", "/") and not parsed.query and not parsed.fragment and
                 any(ip in network for network in PRIVATE_NETWORKS))
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Use http://<private IPv4 address>:3000 without a path or credentials")
    return f"http://{ip}:3000"


class RegisterVMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(max_length=100)
    _validate_url = field_validator("base_url")(normalise_vm_url)


def local_vm():
    ip = os.getenv("DSFST_VM_IP", "127.0.0.1")
    return {"vm_id": "local", "name": os.getenv("DSFST_VM_NAME", socket.gethostname()),
            "base_url": f"http://{ip}:3000", "is_local": True}


class VMRegistry:
    def __init__(self, get_db):
        self.get_db = get_db

    def get(self, vm_id):
        if vm_id == "local":
            return local_vm()
        try:
            vm = self.get_db()["vms"].find_one({"vm_id": vm_id}, {"_id": 0})
        except PyMongoError as error:
            raise HTTPException(503, "VM registry database unavailable") from error
        if not vm:
            raise HTTPException(404, "VM not registered")
        return vm

    def list(self):
        try:
            return [local_vm(), *self.get_db()["vms"].find({}, {"_id": 0}).sort("name", 1)]
        except PyMongoError as error:
            raise HTTPException(503, "VM registry database unavailable") from error

    def add(self, body):
        if body.base_url == local_vm()["base_url"]:
            raise HTTPException(409, "This VM is already available as local")
        vm = {"vm_id": str(uuid.uuid4()), "name": body.name,
              "base_url": body.base_url, "is_local": False}
        try:
            collection = self.get_db()["vms"]
            collection.create_index("vm_id", unique=True)
            collection.create_index("base_url", unique=True)
            collection.insert_one(dict(vm))
        except DuplicateKeyError as error:
            raise HTTPException(409, "This VM address is already registered") from error
        except PyMongoError as error:
            raise HTTPException(503, "VM registry database unavailable") from error
        return vm

    def remove(self, vm_id):
        if vm_id == "local":
            raise HTTPException(409, "The local VM cannot be removed")
        self.get(vm_id)
        try:
            db = self.get_db()
            if db["experiment_batches"].find_one(
                    {"vm_ids": vm_id, "status": {"$in": ACTIVE_BATCH_STATES}}):
                raise HTTPException(409, "Stop or finish this VM's batches before removing it")
            result = db["vms"].delete_one({"vm_id": vm_id})
            if result.deleted_count != 1:
                raise HTTPException(404, "VM not registered")
        except PyMongoError as error:
            raise HTTPException(503, "VM registry database unavailable") from error
        return {"vm_id": vm_id, "removed": True}


def vm_request(vm, port, path, method="GET", payload=None):
    """Only service-owned paths/ports; do not follow redirects or use host proxies."""
    if port not in (8008, 8009):
        raise ValueError("Unsupported VM service")
    if vm.get("is_local"):
        url = f"http://127.0.0.1:{port}{path}"
    else:
        url = normalise_vm_url(vm["base_url"]) + f"/api/{port}{path}"
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(method, url, json=payload,
                                       timeout=(3, 18), allow_redirects=False)
            if not 200 <= response.status_code < 300:
                try:
                    detail = response.json().get("detail", f"HTTP {response.status_code}")
                except (ValueError, AttributeError):
                    detail = f"HTTP {response.status_code}"
                raise HTTPException(response.status_code if response.status_code in
                                    (404, 409, 422, 503) else 502,
                                    f"{vm['name']}: {detail}")
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
            return data
    except requests.RequestException as error:
        raise HTTPException(503, f"{vm['name']}: VM API unavailable") from error
    except ValueError as error:
        raise HTTPException(502, f"{vm['name']}: invalid VM response") from error
