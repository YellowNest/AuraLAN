"""Dependency-free Prometheus exposition for aggregate AuraLAN health."""

from __future__ import annotations

from typing import Any


def _number(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _metric(lines: list[str], name: str, help_text: str, value: object) -> None:
    rendered = _number(value)
    if rendered is None:
        return
    lines.extend((
        f"# HELP {name} {help_text}",
        f"# TYPE {name} gauge",
        f"{name} {rendered}",
    ))


def render_prometheus(snapshot: dict[str, Any]) -> str:
    """Render aggregate metrics without device identities, addresses, or notes."""
    devices = snapshot.get("devices") or []
    services = (snapshot.get("services") or {}).get("items") or []
    host = snapshot.get("host") or {}
    errors = snapshot.get("errors") or []
    monitor = snapshot.get("monitor") or {}

    current_devices = [device for device in devices if device.get("state") != "known"]
    online_devices = [device for device in current_devices if device.get("online") is True]
    remembered_devices = [device for device in devices if device.get("state") == "known"]
    detected_services = [service for service in services if service.get("detected")]
    online_services = [service for service in detected_services if service.get("state") == "online"]

    lines: list[str] = []
    _metric(lines, "auralan_up", "AuraLAN produced a system snapshot.", 1)
    _metric(lines, "auralan_devices_total", "Devices in the AuraLAN inventory.", len(devices))
    _metric(lines, "auralan_devices_current", "Devices represented by the current discovery pass.", len(current_devices))
    _metric(lines, "auralan_devices_online", "Current devices with positive online evidence.", len(online_devices))
    _metric(lines, "auralan_devices_not_seen_now", "Remembered devices absent from the current discovery pass.", len(remembered_devices))
    _metric(lines, "auralan_services_detected", "Optional local services detected by AuraLAN.", len(detected_services))
    _metric(lines, "auralan_services_online", "Detected local services reporting online.", len(online_services))
    _metric(lines, "auralan_discovery_errors", "Discovery warnings in the latest AuraLAN snapshot.", len(errors))
    _metric(lines, "auralan_monitor_enabled", "Whether continuous background monitoring is enabled.", 1 if monitor.get("enabled") else 0)
    _metric(lines, "auralan_monitor_running", "Whether the background monitor thread is currently running.", 1 if monitor.get("running") else 0)
    _metric(lines, "auralan_monitor_interval_seconds", "Configured continuous monitoring interval in seconds.", monitor.get("interval_seconds"))
    _metric(lines, "auralan_monitor_last_success_timestamp_seconds", "Unix timestamp of the latest successful background discovery pass.", monitor.get("last_success_at"))
    _metric(lines, "auralan_host_memory_used_percent", "Host memory currently used, percent.", host.get("memory_used_percent"))
    _metric(lines, "auralan_host_storage_used_percent", "Root filesystem storage currently used, percent.", host.get("storage_used_percent"))
    _metric(lines, "auralan_host_temperature_celsius", "Host temperature in degrees Celsius when available.", host.get("temperature_celsius"))

    return "\n".join(lines) + "\n"
