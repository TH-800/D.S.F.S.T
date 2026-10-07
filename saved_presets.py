"""SCRUM-16 API support, generated with OpenAI Codex assistance.

Uses the saved_presets fields and failure types proposed in SCRUM-15.
Saving/loading configuration never starts an experiment.
"""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymongo.errors import PyMongoError

from experiment_parameters import normalise_parameters

TYPE_MAP = {
    "cpu_stress": "cpu", "memory_stress": "memory",
    "network_latency": "latency", "packet_loss": "packet_loss",
}
REQUIRED_PARAMETERS = {
    "cpu_stress": {"cpu_percent", "duration_seconds"},
    "memory_stress": {"memory_mb", "duration_seconds"},
    "network_latency": {"latency_ms"},
    "packet_loss": {"packet_loss_percent"},
}


class PresetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    failure_type: Literal["cpu_stress", "memory_stress", "network_latency", "packet_loss"]
    parameters: dict

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_parameters(self):
        if set(self.parameters) != REQUIRED_PARAMETERS[self.failure_type]:
            raise ValueError("Supply exactly the parameters required for this failure type")
        self.parameters = normalise_parameters(TYPE_MAP[self.failure_type], self.parameters)
        return self


def register_preset_routes(app, get_db, serialise):
    def output(doc):
        # Mongo stores UTC dates at millisecond precision and may return them naive.
        result = serialise(doc)
        for field in ("created_at", "updated_at"):
            value = doc.get(field)
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                result[field] = value.astimezone(timezone.utc).isoformat(timespec="milliseconds")
        return result

    router = APIRouter(prefix="/presets", tags=["Saved presets"])

    @router.get("")
    def list_presets(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
        try:
            docs = (get_db()["saved_presets"].find({}, {"_id": 0})
                    .sort([("created_at", -1), ("preset_id", 1)]).skip(offset).limit(limit))
            return [output(doc) for doc in docs]
        except PyMongoError:
            raise HTTPException(503, "Preset database is unavailable")

    @router.post("", status_code=201)
    def save_preset(preset: PresetInput, request: Request):
        origin = request.headers.get("origin")
        if origin and origin not in {"http://localhost:3000", "http://127.0.0.1:3000"}:
            raise HTTPException(403, "Use this VM's dashboard to save presets")
        now = datetime.now(timezone.utc)
        doc = {
            **preset.model_dump(), "preset_id": str(uuid4()),
            # No authenticated user identity is available in this application.
            "created_by": "local", "created_at": now, "updated_at": now,
        }
        try:
            get_db()["saved_presets"].insert_one(doc)
        except PyMongoError:
            raise HTTPException(503, "Preset database is unavailable; preset was not confirmed saved")
        return output(doc)

    @router.get("/{preset_id}")
    def load_preset(preset_id: str):
        try:
            doc = get_db()["saved_presets"].find_one({"preset_id": preset_id}, {"_id": 0})
        except PyMongoError:
            raise HTTPException(503, "Preset database is unavailable")
        if doc is None:
            raise HTTPException(404, "Preset not found")
        return output(doc)

    app.include_router(router)
