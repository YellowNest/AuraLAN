from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..command import command_exists, run_command


def _container_mode() -> bool:
    return os.environ.get("AURALAN_CONTAINER_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _pihole_paths() -> tuple[Path, Path]:
    root = Path(os.environ.get("AURALAN_PIHOLE_DIR", "/etc/pihole")).expanduser()
    configured_db = os.environ.get("AURALAN_PIHOLE_FTL_DB", "").strip()
    database = Path(configured_db).expanduser() if configured_db else root / "pihole-FTL.db"
    return root, database


def _unit_state(name: str) -> str:
    if not command_exists("systemctl"):
        return "unknown"
    result = run_command(["systemctl", "is-active", name])
    if result.output == "active":
        return "online"
    return "offline" if result.output in {"inactive", "failed"} else "unknown"


def _dns_listener_state() -> str:
    """Use the shared network namespace to verify host DNS availability.

    A container cannot reliably query the host systemd manager without giving it
    broader host access than AuraLAN needs. With host networking, however, the
    container shares the host network namespace. A TCP/53 listener therefore
    gives a bounded, read-only runtime signal for a host Pi-hole installation
    that has already been identified from its mounted local files.
    """
    if not command_exists("ss"):
        return "unknown"
    result = run_command(["ss", "-H", "-lnt"], timeout=2.0)
    if result.code != 0:
        return "unknown"

    for line in result.output.splitlines():
        columns = line.split()
        if len(columns) < 4:
            continue
        local = columns[3]
        if local.rsplit(":", 1)[-1] == "53":
            return "online"
    return "offline"


def discover(containers: list[dict[str, Any]]) -> dict[str, Any]:
    container = next((row for row in containers if "pihole" in row["name"].lower() or "pihole" in row["image"].lower()), None)
    if container:
        online = container["state"] == "running"
        return {
            "id": "pihole", "name": "Pi-hole", "detected": True, "state": "online" if online else "offline", "runtime": "docker",
            "summary": "DNS filtering is running" if online else "Container is stopped", "importance": "standard",
            "details": {"container": container["name"], "image": container["image"], "status": container["status"]},
        }

    root, database = _pihole_paths()
    local = root.exists() or database.is_file() or command_exists("pihole")
    if local and _container_mode():
        state = _dns_listener_state()
        if state == "online":
            summary = "DNS filtering is running"
        elif state == "offline":
            summary = "Pi-hole data is available but no TCP DNS listener was found"
        else:
            summary = "Pi-hole data is available; service state is unavailable"
        return {
            "id": "pihole",
            "name": "Pi-hole",
            "detected": True,
            "state": state,
            "runtime": "host",
            "summary": summary,
            "importance": "standard",
            "details": {
                "directory": str(root),
                "ftl_database": str(database) if database.is_file() else None,
                "ftl_database_readable": database.is_file() and os.access(database, os.R_OK),
                "state_source": "host-network-tcp-53",
            },
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
