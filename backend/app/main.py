from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException, Query, Request
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
    MonitorResponse,
    NetworkResponse,
    NotificationStatusResponse,
    ServicesResponse,
    ServiceResponse,
    StatusResponse,
)
from .metrics import render_prometheus
from .monitor import BackgroundMonitor
from .notifications import WebhookNotifier
from .persistence.device_store import store
from .discovery.integrations.base import APP_CAPABILITIES
from .services.system import host, system_snapshot

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

webhook_notifier = WebhookNotifier(store())


def _after_background_snapshot(snapshot: dict) -> None:
    store().record_watch_transitions(snapshot.get("devices") or [])
    webhook_notifier.dispatch_pending()


background_monitor = BackgroundMonitor(
    system_snapshot,
    after_collect=_after_background_snapshot,
)


def _notification_status() -> dict:
    try:
        return webhook_notifier.status()
    except (OSError, sqlite3.Error):
        return {
            "configured": webhook_notifier.enabled,
            "include_identifiers": webhook_notifier.include_identifiers,
            "last_attempt_at": webhook_notifier.last_attempt_at,
            "last_success_at": webhook_notifier.last_success_at,
            "last_error": "StorageUnavailable",
            "pending_events": 0,
        }


@asynccontextmanager
async def lifespan(_: FastAPI):
    background_monitor.start()
    try:
        yield
    finally:
        background_monitor.stop()


app = FastAPI(
    title="AuraLAN",
    version=brand()["version"],
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def safety_headers(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path == "/metrics":
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
    metadata = brand()
    return {
        **system_snapshot(),
        "version": metadata["version"],
        "api_version": metadata["apiVersion"],
        "monitor": background_monitor.status(),
        "notifications": _notification_status(),
    }


@app.get("/api/v1/monitor", response_model=MonitorResponse)
def monitor_status() -> dict:
    return background_monitor.status()


@app.get("/api/v1/notifications", response_model=NotificationStatusResponse)
def notification_status() -> dict:
    return _notification_status()


@app.post("/api/v1/notifications/test", response_model=NotificationStatusResponse)
def test_notification() -> dict:
    if not webhook_notifier.enabled:
        raise HTTPException(status_code=409, detail="AuraLAN webhook notifications are not configured")
    if not webhook_notifier.send_test():
        raise HTTPException(status_code=502, detail="AuraLAN webhook test delivery failed")
    return _notification_status()


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    snapshot = {
        **system_snapshot(),
        "monitor": background_monitor.status(),
        "notifications": _notification_status(),
    }
    return Response(
        render_prometheus(snapshot),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


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
    if "location" in update.model_fields_set:
        kwargs["location"] = update.location.strip() if update.location else None
    if "tags" in update.model_fields_set:
        raw_tags = update.tags or []
        normalized_tags: list[str] = []
        seen_tags: set[str] = set()
        for raw_tag in raw_tags:
            tag = str(raw_tag).strip()
            if not tag:
                continue
            if len(tag) > 24:
                raise HTTPException(status_code=422, detail="Device tags must be 24 characters or fewer")
            key = tag.casefold()
            if key in seen_tags:
                continue
            seen_tags.add(key)
            normalized_tags.append(tag)
        kwargs["tags"] = normalized_tags
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
def activity_status(limit: int = Query(default=50, ge=1, le=100)) -> dict:
    try:
        return {"items": store().recent_events(limit)}
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="AuraLAN activity history is unavailable") from exc


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
        "network": snapshot["network"], "services": snapshot["services"],
        "monitor": background_monitor.status(), "notifications": _notification_status(),
        "discovery_errors": snapshot["errors"],
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
