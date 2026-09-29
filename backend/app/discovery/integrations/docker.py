from __future__ import annotations

import json
from typing import Any

from ..command import command_exists, run_command


def parse_docker_inspect(output: str) -> list[dict[str, Any]]:
    try:
        raw = json.loads(output)
    except ValueError:
        return []
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw:
        state = item.get("State") or {}
        config = item.get("Config") or {}
        host_config = item.get("HostConfig") or {}
        name = str(item.get("Name") or "").lstrip("/")
        if not name:
            continue
        health = state.get("Health") or {}
        ports = []
        for container_port, bindings in (item.get("NetworkSettings", {}).get("Ports") or {}).items():
            if bindings:
                ports.extend(f"{binding.get('HostPort')}→{container_port}" for binding in bindings if binding.get("HostPort"))
        rows.append(
            {
                "name": name,
                "image": str(config.get("Image") or "unknown"),
                "state": "running" if state.get("Running") else str(state.get("Status") or "unknown").lower(),
                "status": str(state.get("Status") or "unknown"),
                "network_mode": host_config.get("NetworkMode"),
                "ports": ", ".join(ports) or None,
                "health": health.get("Status"),
            }
        )
    return rows


def containers() -> tuple[bool, list[dict[str, Any]], str | None]:
    if not command_exists("docker"):
        return False, [], "Docker binary is unavailable"
    names = run_command(["docker", "ps", "-a", "--format", "{{.Names}}"], timeout=3.0)
    if names.code != 0:
        return True, [], names.error or names.output or "Docker could not be queried"
    container_names = [line.strip() for line in names.output.splitlines() if line.strip()][:100]
    if not container_names:
        return True, [], None
    inspected = run_command(["docker", "inspect", *container_names], timeout=4.0)
    if inspected.code != 0:
        return True, [], inspected.error or inspected.output or "Docker inspection failed"
    return True, parse_docker_inspect(inspected.output), None


def discover() -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    detected, rows, error = containers()
    running = sum(1 for row in rows if row["state"] == "running")
    unhealthy = sum(1 for row in rows if row.get("health") == "unhealthy")
    stopped = max(0, len(rows) - running)
    state = "unknown" if error else ("online" if detected else "unknown")
    return (
        {
            "id": "docker",
            "name": "Docker",
            "detected": detected,
            "state": state,
            "runtime": "docker" if detected else None,
            "summary": f"{running} running" if detected else "Not detected",
            "importance": "standard",
            "details": {"running": running, "total": len(rows), "stopped": stopped, "unhealthy": unhealthy, "containers": rows},
        },
        rows,
        error,
    )
