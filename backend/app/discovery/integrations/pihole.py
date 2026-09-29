from __future__ import annotations

from pathlib import Path
from typing import Any

from ..command import command_exists, run_command


def _unit_state(name: str) -> str:
    if not command_exists("systemctl"):
        return "unknown"
    result = run_command(["systemctl", "is-active", name])
    if result.output == "active":
        return "online"
    return "offline" if result.output in {"inactive", "failed"} else "unknown"


def discover(containers: list[dict[str, Any]]) -> dict[str, Any]:
    container = next((row for row in containers if "pihole" in row["name"].lower() or "pihole" in row["image"].lower()), None)
    local = Path("/etc/pihole").exists() or command_exists("pihole")
    if container:
        online = container["state"] == "running"
        return {
            "id": "pihole", "name": "Pi-hole", "detected": True, "state": "online" if online else "offline", "runtime": "docker",
            "summary": "DNS filtering is running" if online else "Container is stopped", "importance": "standard",
            "details": {"container": container["name"], "image": container["image"], "status": container["status"]},
        }
    if local:
        state = _unit_state("pihole-FTL.service")
        return {
            "id": "pihole", "name": "Pi-hole", "detected": True, "state": state, "runtime": "systemd",
            "summary": "DNS filtering is running" if state == "online" else "Service state is unavailable", "importance": "standard", "details": {"unit": "pihole-FTL.service"},
        }
    return {
        "id": "pihole", "name": "Pi-hole", "detected": False, "state": "unknown", "runtime": None,
        "summary": "Not detected", "importance": "optional", "details": {},
    }
