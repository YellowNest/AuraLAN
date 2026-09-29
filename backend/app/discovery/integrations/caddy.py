from __future__ import annotations

from typing import Any

from ..command import command_exists, run_command


def _systemd_state(unit: str) -> str:
    if not command_exists("systemctl"):
        return "unknown"
    result = run_command(["systemctl", "is-active", unit])
    if result.output == "active":
        return "online"
    return "offline" if result.output in {"inactive", "failed", "deactivating"} else "unknown"


def discover(containers: list[dict[str, Any]]) -> dict[str, Any]:
    """Caddy may be systemd-native or run in Docker with host networking."""
    native_state = _systemd_state("caddy.service")
    if native_state == "online":
        return {
            "id": "caddy", "name": "Caddy", "detected": True, "state": "online", "runtime": "systemd",
            "summary": "Reverse proxy is running", "importance": "standard", "details": {"unit": "caddy.service"},
        }
    match = next(
        (row for row in containers if "caddy" in row["name"].lower() or "caddy" in row["image"].lower()),
        None,
    )
    if match:
        online = match["state"] == "running"
        return {
            "id": "caddy", "name": "Caddy", "detected": True, "state": "online" if online else "offline", "runtime": "docker",
            "summary": "Reverse proxy is running" if online else "Container is stopped", "importance": "standard",
            "details": {"container": match["name"], "image": match["image"], "status": match["status"], "network_mode": match.get("network_mode")},
        }
    if native_state == "offline" or command_exists("caddy"):
        return {
            "id": "caddy", "name": "Caddy", "detected": True, "state": native_state, "runtime": "systemd",
            "summary": "Service is not running" if native_state == "offline" else "State could not be determined", "importance": "standard", "details": {"unit": "caddy.service"},
        }
    return {
        "id": "caddy", "name": "Caddy", "detected": False, "state": "unknown", "runtime": None,
        "summary": "Not detected", "importance": "optional", "details": {},
    }
