"""Read-only system snapshot orchestration with short-lived discovery caching."""

from __future__ import annotations

import os
import shutil
import sqlite3
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from ..discovery.integrations import caddy, docker, pihole, wireguard
from ..discovery.integrations.base import enrich as enrich_integration
from ..discovery.network import devices, dnsmasq, iproute, iw, networkmanager
from ..persistence.device_store import store

CACHE_TTL_SECONDS = 2.0
_cache_lock = threading.Lock()
_cache: tuple[float, dict[str, Any]] | None = None


def _hostname() -> str:
    return socket.gethostname() or "localhost"


def _uptime() -> str:
    try:
        seconds = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return "Unknown"
    days, remainder = divmod(int(seconds), 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    return f"{days}d {hours}h" if days else f"{hours}h {minutes}m"


def _memory_used_percent() -> int | None:
    try:
        fields = {line.split(":", 1)[0]: int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line}
        total, available = fields.get("MemTotal", 0), fields.get("MemAvailable", 0)
        return round((total - available) * 100 / total) if total else None
    except (OSError, ValueError, IndexError):
        return None


def _temperature() -> float | None:
    for path in (Path("/sys/class/thermal/thermal_zone0/temp"), Path("/sys/devices/virtual/thermal/thermal_zone0/temp")):
        try:
            raw = float(path.read_text().strip())
            value = raw / 1000 if raw > 1000 else raw
            return round(value, 1) if -20 < value < 150 else None
        except (OSError, ValueError):
            continue
    return None


def host() -> dict[str, Any]:
    try:
        disk = shutil.disk_usage("/")
        storage = round(disk.used * 100 / disk.total)
    except OSError:
        storage = None
    try:
        load = " · ".join(f"{value:.2f}" for value in os.getloadavg())
    except OSError:
        load = "Unknown"
    return {"name": _hostname(), "uptime": _uptime(), "load": load, "memory_used_percent": _memory_used_percent(), "storage_used_percent": storage, "temperature_celsius": _temperature()}


def _access_point() -> tuple[dict[str, Any], bool]:
    """Find an AP across NetworkManager and plain iw without fixed interface names.

    The boolean indicates whether the operator explicitly requested an AP
    interface. A normal Linux host may be a Wi-Fi client and should not be
    treated as unhealthy merely because it is not itself an access point.
    """
    preferred = os.environ.get("AURALAN_WIFI_INTERFACE", "").strip() or None
    nm_candidates = networkmanager.wifi_candidates(preferred)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    if preferred:
        candidates.append({"interface": preferred, "connection": None, "ssid": None, "channel": None})
        seen.add(preferred)

    for row in nm_candidates:
        interface = str(row.get("interface") or "")
        if interface and interface not in seen:
            candidates.append(row)
            seen.add(interface)

    for row in iw.wireless_interfaces():
        interface = str(row.get("name") or "")
        if interface and interface not in seen:
            candidates.append({"interface": interface, "connection": None, "ssid": None, "channel": None})
            seen.add(interface)

    ap_expected = preferred is not None
    for candidate in candidates:
        wireless = iw.interface_info(candidate.get("interface"))
        if wireless.get("type") != "AP":
            continue
        return ({
            "available": True,
            "connection": candidate.get("connection"),
            "interface": candidate.get("interface"),
            "ssid": wireless.get("ssid") or candidate.get("ssid"),
            "channel": wireless.get("channel") or candidate.get("channel"),
            "band": wireless.get("band"),
            "frequency_mhz": wireless.get("frequency_mhz"),
            "ipv4": None,
            "subnet": None,
            "state": "online",
        }, ap_expected)

    return ({
        "available": False,
        "connection": None,
        "interface": None,
        "ssid": None,
        "channel": None,
        "band": None,
        "frequency_mhz": None,
        "ipv4": None,
        "subnet": None,
        "state": "unknown",
    }, ap_expected)


def discover_network() -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    access_point, ap_expected = _access_point()

    route_rows = iproute.routes()
    default = iproute.default_route(route_rows)
    interface_rows = iproute.interfaces(access_point["interface"], default["interface"])
    access_point["ipv4"] = iproute.ipv4_for(interface_rows, access_point["interface"])
    access_point["subnet"] = access_point["ipv4"]

    uplink_ip = iproute.ipv4_for(interface_rows, default["interface"])
    uplink = {
        "interface": default["interface"],
        "gateway": default["gateway"],
        "ipv4": uplink_ip,
        "state": "online" if default["interface"] else "unknown",
    }

    dhcp, lease_entries = dnsmasq.discover(access_point["interface"])
    signals = iw.station_signals(access_point["interface"]) if access_point["available"] else {}
    device_rows, device_errors = devices.collect_devices(interface_rows, lease_entries, signals)
    errors.extend(device_errors)

    if ap_expected and not access_point["available"]:
        errors.append("Configured Wi-Fi interface could not be confirmed in AP mode")

    routes = [
        {key: str(row[key]) for key in ("dst", "gateway", "dev", "protocol") if row.get(key) is not None}
        for row in route_rows
    ]
    return ({"access_point": access_point, "uplink": uplink, "dhcp": dhcp, "interfaces": interface_rows, "routes": routes}, device_rows, errors)


def system_state(network: dict[str, Any], service_items: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    attention = [item for item in service_items if item["detected"] and item["state"] == "offline"]
    if attention:
        count = len(attention)
        return {"state": "degraded", "title": f"{count} service needs attention", "summary": "A detected service is not reporting as online.", "attention_count": count}
    if errors:
        return {"state": "warning", "title": "Some details are unavailable", "summary": "Core status is available; one discovery source needs attention.", "attention_count": len(errors)}
    return {"state": "healthy", "title": "Everything looks good", "summary": "Local network discovery and detected services are responding normally.", "attention_count": 0}


def _collect() -> dict[str, Any]:
    errors: list[str] = []
    try:
        network, device_rows, network_errors = discover_network()
        errors.extend(network_errors)
    except Exception as exc:  # One subsystem must never blank the whole dashboard.
        network = {"access_point": {"available": False, "state": "unknown"}, "uplink": {"state": "unknown"}, "dhcp": {"detected": False, "state": "unknown", "lease_count": 0}, "interfaces": [], "routes": []}
        device_rows = []
        errors.append(f"Network discovery unavailable: {type(exc).__name__}")
    try:
        docker_service, containers, docker_error = docker.discover()
        if docker_error:
            errors.append(f"Docker discovery: {docker_error}")
    except Exception as exc:
        docker_service, containers = ({"id": "docker", "name": "Docker", "detected": False, "state": "unknown", "runtime": None, "summary": "Unavailable", "importance": "optional", "details": {}}, [])
        errors.append(f"Docker discovery unavailable: {type(exc).__name__}")
    integrations: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("pihole", lambda: pihole.discover(containers)),
        ("wireguard", lambda: wireguard.discover(network["interfaces"], containers)),
        ("caddy", lambda: caddy.discover(containers)),
    ]
    service_items = [docker_service]
    for identifier, provider in integrations:
        try:
            service_items.append(provider())
        except Exception as exc:
            errors.append(f"{identifier} discovery unavailable: {type(exc).__name__}")
    service_items = [enrich_integration(item) for item in service_items]
    try:
        activity = store().recent_events(20)
    except (OSError, sqlite3.Error):
        activity = []
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "system": system_state(network, service_items, errors),
        "host": host(),
        "network": network,
        "devices": device_rows,
        "services": {"items": service_items},
        "activity": activity,
        "errors": errors,
    }


def system_snapshot(force: bool = False) -> dict[str, Any]:
    """Return one bounded snapshot and collapse concurrent cache misses.

    Discovery is the expensive part of AuraLAN. Keep the cache lock across a
    refresh so simultaneous HTTP requests cannot launch duplicate discovery
    passes. Timestamp the cache after collection; otherwise a slow-but-valid
    refresh can already be expired by the time it finishes.
    """
    global _cache
    with _cache_lock:
        now = time.monotonic()
        if not force and _cache and now - _cache[0] < CACHE_TTL_SECONDS:
            return _cache[1]
        snapshot = _collect()
        _cache = (time.monotonic(), snapshot)
        return snapshot
