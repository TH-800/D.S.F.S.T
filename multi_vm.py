"""VM registration and durable parallel experiment batches."""
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.errors import PyMongoError
from vm_registry import RegisterVMRequest, ACTIVE_BATCH_STATES, vm_request

TERMINAL_MEMBERS = {"completed", "stopped", "not_started", "created"}
ACTIVE_MEMBERS = {"running", "unknown", "pending"}
BATCH_LEASE_SECONDS = 180


def utcnow():
    return datetime.now(timezone.utc)


def parallel(items, operation):
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(len(items), 16)) as pool:
        return list(pool.map(operation, items))


def public(doc):
    return {key: value for key, value in doc.items() if key != "_id"}


class LaunchBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, max_length=120)
    failure_type: Literal["cpu", "memory", "latency", "packet_loss"]
    target_container: Literal["host"] = "host"
    parameters: dict = Field(default_factory=dict)
    vm_ids: list[str] = Field(min_length=1, max_length=16)

    @field_validator("vm_ids")
    @classmethod
    def unique_ids(cls, values):
        if len(set(values)) != len(values) or any(not v.strip() for v in values):
            raise ValueError("Select unique, nonempty VM IDs")
        return values


class BatchManager:
    def __init__(self, get_db, registry, normalise_parameters):
        self.get_db = get_db
        self.registry = registry
        self.normalise_parameters = normalise_parameters

    def collection(self):
        return self.get_db()["experiment_batches"]

    def load(self, batch_id):
        try:
            result = self.collection().find_one({"batch_id": batch_id}, {"_id": 0})
        except PyMongoError as error:
            raise HTTPException(503, "Batch database unavailable") from error
        if not result:
            raise HTTPException(404, "Batch not found")
        return result

    def member_record(self, member):
        return vm_request(member["vm"], 8008,
                          "/experiments/" + quote(member["experiment_id"], safe=""))

    def created_is_inactive(self, member):
        if not member.get("start_attempted"):
            return True
        # HTTP 409 from the start route is a rejection before injection.
        # Confirm that this child's ID did not become the active experiment.
        if member.get("start_error_code") == 409:
            state = vm_request(member["vm"], 8009, "/state")
            return (state.get("state") in ("idle", "complete", "running") and
                    state.get("active_experiment_id") != member["experiment_id"])
        return False

    def stop_member(self, member):
        member = copy.deepcopy(member)
        if not member.get("experiment_id"):
            member.update(status="not_started", error=member.get("error"))
            return member
        try:
            record = self.member_record(member)
            if record.get("status") in ("completed", "stopped", "failed") or (
                    record.get("status") == "created" and self.created_is_inactive(member)):
                member.update(status=record["status"], error=None)
                return member
        except HTTPException:
            # A failed read does not prevent trying a reset for a known child.
            pass
        try:
            result = vm_request(member["vm"], 8009,
                                f"/experiments/{quote(member['experiment_id'], safe='')}/stop",
                                "POST")
            if result.get("status") != "completed":
                raise HTTPException(502, "VM did not confirm the reset")
            member.update(status="completed", error=None)
        except HTTPException as error:
            # Completion can race with a manual stop; confirm the stored outcome.
            try:
                record = self.member_record(member)
                if record.get("status") in ("completed", "stopped") or (
                        record.get("status") == "created" and self.created_is_inactive(member)):
                    member.update(status=record["status"], error=None)
                    return member
            except HTTPException:
                pass
            member.update(status="unknown", error=str(error.detail))
        return member

    def launch(self, body):
        try:
            parameters = self.normalise_parameters(body.failure_type, body.parameters)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        vms = [self.registry.get(vm_id) for vm_id in body.vm_ids]

        def preflight(vm):
            try:
                state = vm_request(vm, 8009, "/state")
                if state.get("state") not in ("idle", "complete") or state.get("active_experiment_id"):
                    return {"vm_id": vm["vm_id"], "error": "VM is busy or its state is unknown",
                            "status": 409}
                return None
            except HTTPException as error:
                return {"vm_id": vm["vm_id"], "error": str(error.detail), "status": error.status_code}

        errors = [error for error in parallel(vms, preflight) if error]
        if errors:
            raise HTTPException(409 if all(e["status"] == 409 for e in errors) else 503,
                                {"message": "No experiment was started; VM preflight failed",
                                 "vms": errors})
        now = utcnow()
        batch = {"batch_id": str(uuid.uuid4()), "name": body.name or f"{body.failure_type} batch",
                 "failure_type": body.failure_type, "parameters": parameters,
                 "vm_ids": body.vm_ids, "status": "starting", "created_at": now,
                 "started_at": now, "ended_at": None,
                 "lease_until": now + timedelta(seconds=BATCH_LEASE_SECONDS),
                 "members": [{"vm_id": vm["vm_id"], "vm_name": vm["name"],
                              "vm": vm, "experiment_id": None,
                              "status": "pending", "error": None, "start_attempted": False} for vm in vms]}
        try:
            self.collection().insert_one(copy.deepcopy(batch))
        except PyMongoError as error:
            raise HTTPException(503, "Could not save batch; no experiment was started") from error

        def launch_one(index):
            member = batch["members"][index]
            try:
                result = vm_request(member["vm"], 8009, "/experiments", "POST",
                                    {"name": batch["name"], "failure_type": body.failure_type,
                                     "target_container": "host", "parameters": parameters})
                child_id = str(uuid.UUID(result["experiment_id"]))
                member["experiment_id"] = child_id
                # Persist the child identity BEFORE starting it, so stop survives a restart.
                self.collection().update_one({"batch_id": batch["batch_id"]},
                    {"$set": {f"members.{index}.experiment_id": child_id,
                              f"members.{index}.start_attempted": True}})
                member["start_attempted"] = True
                started = vm_request(member["vm"], 8009, f"/experiments/{child_id}/start", "POST", {})
                if started.get("status") != "running":
                    raise HTTPException(502, "VM did not confirm experiment startup")
                member["status"] = "running"
            except (HTTPException, PyMongoError, ValueError, KeyError) as error:
                member["status"] = "unknown" if member["experiment_id"] else "not_started"
                member["error"] = str(error.detail if isinstance(error, HTTPException) else error)
                if isinstance(error, HTTPException):
                    member["start_error_code"] = error.status_code
            return member

        batch["members"] = parallel(list(range(len(vms))), launch_one)
        failures = [m for m in batch["members"] if m["status"] != "running"]
        if failures:
            batch["launch_errors"] = [{"vm_id": m["vm_id"], "error": m["error"]} for m in failures]
            batch["members"] = parallel(batch["members"], self.stop_member)
            batch["status"] = ("partial_failure" if any(m["status"] in ACTIVE_MEMBERS
                               for m in batch["members"]) else "failed")
        else:
            batch["status"] = "running"
        if batch["status"] == "failed":
            batch["ended_at"] = utcnow()
        try:
            self.collection().update_one({"batch_id": batch["batch_id"]}, {"$set": public(batch)})
        except PyMongoError as error:
            # If final journaling fails, reset every child; don't leave an untracked launch.
            batch["members"] = parallel(batch["members"], self.stop_member)
            try:
                self.collection().update_one({"batch_id": batch["batch_id"]},
                    {"$set": {"members": batch["members"], "status": "partial_failure"}})
            except PyMongoError:
                pass
            raise HTTPException(503, {"message": "Batch persistence failed; resets attempted",
                                      "batch_id": batch["batch_id"],
                                      "members": batch["members"]}) from error
        return batch

    def refresh(self, batch):
        status = batch["status"]
        lease = batch.get("lease_until")
        if lease and lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        stale_operation = status in ("starting", "stopping") and (not lease or lease < utcnow())
        if status not in ("running", "partial_failure") and not stale_operation:
            return batch

        def read(member):
            member = copy.deepcopy(member)
            if not member.get("experiment_id"):
                member.update(status="not_started", error=member.get("error"))
                return member
            try:
                record = self.member_record(member)
                state = record.get("status")
                if state == "created" and not self.created_is_inactive(member):
                    raise HTTPException(502, "VM has not persisted startup; reset confirmation is required")
                if state not in ("running", "completed", "stopped", "created", "failed"):
                    raise HTTPException(502, "Unknown child experiment status")
                member.update(status=state, error=None)
            except HTTPException as error:
                member.update(status="unknown", error=str(error.detail))
            return member

        members = parallel(batch["members"], read)
        if all(m["status"] in ("completed", "stopped") for m in members):
            new_status = "failed" if batch.get("launch_errors") else "completed"
        elif (any(m["status"] == "running" for m in members) and
              all(m["status"] in ("running", "completed", "stopped") for m in members) and
              not batch.get("launch_errors")):
            # Timed children can finish on different polls. The batch remains
            # running until every child completes; successful early completion
            # is not a partial failure.
            new_status = "running"
        elif all(m["status"] in TERMINAL_MEMBERS | {"failed"} for m in members):
            new_status = "failed"
        else:
            new_status = "partial_failure"
        fields = {"members": members, "status": new_status}
        if new_status in ("completed", "failed"):
            fields["ended_at"] = utcnow()
        try:
            claim = {"batch_id": batch["batch_id"], "status": status}
            if status == "stopping":
                claim["operation_id"] = batch.get("operation_id")
            self.collection().update_one(claim, {"$set": fields})
            return self.load(batch["batch_id"])
        except PyMongoError as error:
            raise HTTPException(503, "Could not reconcile batch status") from error

    def stop_active(self):
        try:
            batches = list(self.collection().find(
                {"status": {"$in": ACTIVE_BATCH_STATES}}, {"_id": 0}))
        except PyMongoError as error:
            raise HTTPException(503, "Batch database unavailable") from error
        def stop_one(batch):
            try:
                return self.stop(batch["batch_id"])
            except HTTPException as error:
                return {"batch_id": batch["batch_id"], "status": "partial_failure",
                        "error": str(error.detail)}
        return parallel(batches, stop_one)

    def stop(self, batch_id):
        batch = self.refresh(self.load(batch_id))
        if batch["status"] in ("completed", "stopped", "failed"):
            return batch
        if batch["status"] in ("starting", "stopping"):
            raise HTTPException(409, "Batch operation is still in progress; retry its status")
        operation_id = str(uuid.uuid4())
        try:
            claimed = self.collection().find_one_and_update(
                {"batch_id": batch_id, "status": batch["status"]},
                {"$set": {"status": "stopping", "operation_id": operation_id,
                          "lease_until": utcnow() + timedelta(seconds=BATCH_LEASE_SECONDS)}})
            if not claimed:
                raise HTTPException(409, "Another batch operation is in progress")
            members = parallel(batch["members"], self.stop_member)
            status = "partial_failure" if any(m["status"] in ACTIVE_MEMBERS for m in members) else "stopped"
            self.collection().update_one(
                {"batch_id": batch_id, "status": "stopping", "operation_id": operation_id},
                {"$set": {"members": members, "status": status,
                          "ended_at": utcnow() if status == "stopped" else None}})
        except PyMongoError as error:
            raise HTTPException(503, "Batch database unavailable; inspect child states") from error
        return self.load(batch_id)


def build_orchestrator_router(registry, manager):
    router = APIRouter(tags=["VMs and multi-VM experiments"])

    @router.get("/vms")
    def list_vms():
        return registry.list()

    @router.post("/vms", status_code=201)
    def register_vm(body: RegisterVMRequest):
        return registry.add(body)

    @router.delete("/vms/{vm_id}")
    def remove_vm(vm_id: str):
        return registry.remove(vm_id)

    @router.post("/experiments/launch", status_code=201)
    def launch_batch(body: LaunchBatchRequest):
        batch = manager.launch(body)
        return JSONResponse(status_code=201 if batch["status"] == "running" else 207,
                            content=jsonable_encoder(public(batch)))

    @router.get("/experiment-batches")
    def list_batches(limit: int = Query(default=10, ge=1, le=50), active_only: bool = False):
        try:
            query = {"status": {"$in": ACTIVE_BATCH_STATES}} if active_only else {}
            docs = list(manager.collection().find(query, {"_id": 0}).sort("created_at", -1).limit(limit))
            return parallel(docs, manager.refresh)
        except PyMongoError as error:
            raise HTTPException(503, "Batch database unavailable") from error

    @router.post("/experiment-batches/emergency-stop")
    def stop_all_batches():
        batches = manager.stop_active()
        return {"status": "partial_failure" if any(b["status"] in ACTIVE_BATCH_STATES
                for b in batches) else "stopped", "batches": batches}

    @router.get("/experiment-batches/{batch_id}")
    def get_batch(batch_id: str):
        return manager.refresh(manager.load(batch_id))

    @router.post("/experiment-batches/{batch_id}/stop")
    def stop_batch(batch_id: str):
        batch = manager.stop(batch_id)
        return JSONResponse(status_code=200 if batch["status"] in ("stopped", "completed", "failed") else 207,
                            content=jsonable_encoder(public(batch)))

    return router
