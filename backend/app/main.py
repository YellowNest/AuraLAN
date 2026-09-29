from __future__ import annotations

from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .brand import brand
from .models import (
    ActivityResponse,
    DiagnosticsResponse,
    DevicesResponse,
    DeviceMetadataUpdate,
    DeviceResponse,
    HealthResponse,
    HostResponse,
    MetaResponse,
    NetworkResponse,
    ServicesResponse,
    ServiceResponse,
    StatusResponse,
)
from .persistence.device_store import store
from .discovery.integrations.base import APP_CAPABILITIES
from .services.system import host, system_snapshot

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

app = FastAPI(title="AuraLAN", version=brand()["version"], docs_url=None, redoc_url=None)


@app.middleware("http")
async def safety_headers(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    # Frontend source files are the one canonical production asset set for the
    # framework-free build. Keep them revalidating while this pre-release evolves;
    # a stale app shell is more harmful than an extra local request on a Pi LAN.
    if request.url.path in {"/", "/sw.js", "/manifest.webmanifest"} or request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
    if request.url.path == "/sw.js":
        response.headers["Service-Worker-Allowed"] = "/"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.get("/api/v1/meta", response_model=MetaResponse)
def meta() -> dict:
    return {"brand": brand(), "mode": "local-metadata", "capabilities": APP_CAPABILITIES}


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> dict:
    metadata = brand()
    try:
        store().readiness_check()
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="AuraLAN metadata storage is unavailable") from exc
    return {"ok": True, "mode": "local-metadata", "api_version": metadata["apiVersion"], "version": metadata["version"]}


@app.get("/api/v1/status", response_model=StatusResponse)
def status() -> dict:
    return system_snapshot()


@app.get("/api/v1/host", response_model=HostResponse)
def host_status() -> dict:
    return system_snapshot()["host"]


@app.get("/api/v1/network", response_model=NetworkResponse)
def network_status() -> dict:
    return system_snapshot()["network"]


@app.get("/api/v1/devices", response_model=DevicesResponse)
def device_status() -> dict:
    return {"items": system_snapshot()["devices"]}


@app.get("/api/v1/devices/{device_id}", response_model=DeviceResponse)
def device_detail(device_id: str) -> dict:
    item = next((item for item in system_snapshot()["devices"] if item["id"] == device_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Unknown current device")
    return item


@app.patch("/api/v1/devices/{device_id}/metadata", response_model=DeviceResponse)
def update_device_metadata(device_id: str, update: DeviceMetadataUpdate) -> dict:
    """The sole write endpoint: persist AuraLAN-local device labels only."""
    if not update.model_fields_set:
        raise HTTPException(status_code=422, detail="Provide device metadata to update")
    current = next((item for item in system_snapshot()["devices"] if item["id"] == device_id), None)
    if not current:
        raise HTTPException(status_code=404, detail="Unknown current device")
    kwargs: dict[str, object] = {}
    if "alias" in update.model_fields_set:
        kwargs["alias"] = update.alias.strip() if update.alias else None
    if "category_override" in update.model_fields_set:
        kwargs["category_override"] = update.category_override
    if "note" in update.model_fields_set:
        kwargs["note"] = update.note.strip() if update.note else None
    if "favorite" in update.model_fields_set:
        kwargs["favorite"] = update.favorite
    try:
        store().update_metadata(device_id, **kwargs)
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="AuraLAN metadata storage is unavailable") from exc
    refreshed = system_snapshot(force=True)
    item = next((item for item in refreshed["devices"] if item["id"] == device_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Device disappeared during update")
    return item


@app.get("/api/v1/activity", response_model=ActivityResponse)
def activity_status() -> dict:
    return {"items": system_snapshot()["activity"]}


@app.get("/api/v1/services", response_model=ServicesResponse)
def services_status() -> dict:
    return system_snapshot()["services"]


@app.get("/api/v1/services/{service_id}", response_model=ServiceResponse)
def service_status(service_id: str) -> dict:
    item = next((item for item in system_snapshot()["services"]["items"] if item["id"] == service_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Unknown service")
    return item


@app.get("/api/v1/diagnostics", response_model=DiagnosticsResponse)
def diagnostics() -> dict:
    snapshot = system_snapshot()
    return {
        "generated_at": snapshot["generated_at"], "api_version": brand()["apiVersion"],
        "app_version": brand()["version"], "mode": "local-metadata", "host": snapshot["host"],
        "network": snapshot["network"], "services": snapshot["services"], "discovery_errors": snapshot["errors"],
    }


if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(FRONTEND / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(FRONTEND / "sw.js", media_type="application/javascript")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(FRONTEND / "assets" / "icons" / "favicon.svg", media_type="image/svg+xml")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")
