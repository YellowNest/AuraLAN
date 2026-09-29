"""Privacy-preserving Home Assistant summary helpers."""

from __future__ import annotations

import time
from typing import Any


NEW_DEVICE_WINDOW_SECONDS = 24 * 60 * 60


def home_assistant_summary(
    snapshot: dict[str, Any],
    *,
    version: str,
    api_version: str,
    monitor: dict[str, Any],
    notifications: dict[str, Any],
    wake_on_lan_enabled: bool,
    now: int | None = None,
) -> dict[str, Any]:
    """Build an aggregate-only payload suitable for local automation polling."""
    current_time = int(time.time()) if now is None else int(now)
    devices = list(snapshot.get("devices") or [])
    services = list((snapshot.get("services") or {}).get("items") or [])
    system = snapshot.get("system") or {}

    def favorite(device: dict[str, Any]) -> bool:
        return bool((device.get("metadata") or {}).get("favorite"))

    return {
        "version": version,
        "api_version": api_version,
        "generated_at": snapshot.get("generated_at"),
        "system_state": system.get("state", "unknown"),
        "attention_count": int(system.get("attention_count") or 0),
        "devices_total": len(devices),
        "devices_online": sum(1 for device in devices if device.get("online") is True),
        "devices_not_seen_now": sum(1 for device in devices if device.get("state") == "known"),
        "favorites_total": sum(1 for device in devices if favorite(device)),
        "favorites_not_seen_now": sum(
            1
            for device in devices
            if favorite(device) and device.get("state") == "known"
        ),
        "new_devices_24h": sum(
            1
            for device in devices
            if device.get("first_seen_at") is not None
            and int(device["first_seen_at"]) >= current_time - NEW_DEVICE_WINDOW_SECONDS
        ),
        "services_detected": len(services),
        "services_online": sum(1 for service in services if service.get("state") == "online"),
        "discovery_errors": len(snapshot.get("errors") or []),
        "monitor_running": bool(monitor.get("running")),
        "monitor_last_success_at": monitor.get("last_success_at"),
        "webhook_configured": bool(notifications.get("configured")),
        "webhook_pending_events": int(notifications.get("pending_events") or 0),
        "wake_on_lan_enabled": bool(wake_on_lan_enabled),
    }
