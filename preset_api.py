# AI-assisted SCRUM-16 API glue, using the existing Metrics API database.
# These routes store configuration only; they never call injection endpoints.
from datetime import datetime, timezone
from typing import Any, Dict, Literal
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError
from preset_validation import validate_preset

class PresetInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    failure_type: Literal["cpu", "latency", "packet_loss", "memory"]
    parameters: Dict[str, Any]

def build_presets_router(get_db, serialise):
    router = APIRouter(prefix="/presets", tags=["Saved presets"])

    @router.get("")
    def list_presets(limit: int = Query(default=100, ge=1, le=200)):
        try:
            docs = get_db()["saved_presets"].find({}, {"_id": 0}).sort("created_at", DESCENDING).limit(limit)
            return [serialise(doc) for doc in docs]
        except PyMongoError:
            raise HTTPException(status_code=503, detail="Preset database is unavailable")

    @router.post("", status_code=201)
    def save_preset(body: PresetInput):
        try:
            clean = validate_preset(body.name, body.failure_type, body.parameters)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        doc = {**clean, "preset_id": str(uuid4()), "created_at": datetime.now(timezone.utc)}
        try:
            collection = get_db()["saved_presets"]
            # Same field/index names as the team's saved_presets setup.
            collection.create_index("preset_id", unique=True)
            collection.create_index("name", unique=True)
            collection.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Preset name already exists, or existing preset data violates a unique index")
        except PyMongoError:
            raise HTTPException(status_code=503, detail="Preset database is unavailable; nothing was confirmed saved")
        return serialise(doc)

    @router.get("/{preset_id}")
    def load_preset(preset_id: str):
        try:
            doc = get_db()["saved_presets"].find_one({"preset_id": preset_id}, {"_id": 0})
        except PyMongoError:
            raise HTTPException(status_code=503, detail="Preset database is unavailable")
        if doc is None:
            raise HTTPException(status_code=404, detail="Preset not found")
        return serialise(doc)

    return router
