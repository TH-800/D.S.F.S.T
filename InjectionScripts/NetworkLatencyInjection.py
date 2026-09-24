from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from network_rules import NetworkRuleError, apply_rule, network_interface, reset_rule


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


@app.middleware("http")
async def protect_local_api(request, call_next):
    allowed = {"http://localhost:3000", "http://127.0.0.1:3000"}
    origin = request.headers.get("origin")
    host = request.url.hostname
    if host not in ("localhost", "127.0.0.1") or (origin and origin not in allowed):
        return JSONResponse({"detail": "Local dashboard access only"}, status_code=403)
    return await call_next(request)


@app.get("/")
def read_root():
    return {"message": "Network Latency Injection API", "interface": network_interface()}


@app.post("/inject/latency/{delay_ms}")
def inject_latency(delay_ms: int):
    if not 0 <= delay_ms <= 500:
        raise HTTPException(status_code=422, detail="Latency must be between 0 and 500 ms")
    try:
        result = apply_rule("latency", delay_ms)
    except NetworkRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"container_id": "host", "latency_injected_ms": delay_ms,
            "interface": result["interface"], "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/reset/network")
def reset_network():
    try:
        return reset_rule("latency")
    except NetworkRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
