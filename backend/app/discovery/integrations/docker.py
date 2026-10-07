from __future__ import annotations

import http.client
import json
import os
import re
import socket
from pathlib import Path
from typing import Any

from ..command import command_exists, run_command

MAX_DOCKER_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CONTAINERS = 100
_HEALTH_RE = re.compile(r"\((healthy|unhealthy|starting)\)", re.IGNORECASE)


class _UnixHTTPConnection(http.client.HTTPConnection):
    """Minimal HTTP client for a local Docker Engine UNIX socket."""

    def __init__(self, socket_path: str, timeout: float = 3.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._socket_path)
        self.sock = sock


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


def parse_docker_list(output: str) -> list[dict[str, Any]]:
    """Parse the bounded Docker Engine container-list response.

    The list endpoint gives AuraLAN enough state for service visibility without
    reading container environment variables, bind mounts, labels, or logs.
    """
    try:
        raw = json.loads(output)
    except ValueError:
        return []
    if not isinstance(raw, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in raw[:MAX_CONTAINERS]:
        names = item.get("Names") or []
        name = str(names[0] if names else "").lstrip("/")
        if not name:
            continue

        ports: list[str] = []
        for binding in item.get("Ports") or []:
            public = binding.get("PublicPort")
            private = binding.get("PrivatePort")
            protocol = binding.get("Type") or "tcp"
            if public and private:
                ports.append(f"{public}→{private}/{protocol}")

        status = str(item.get("Status") or item.get("State") or "unknown")
        health_match = _HEALTH_RE.search(status)
        state = str(item.get("State") or "unknown").lower()
        host_config = item.get("HostConfig") or {}

        rows.append(
            {
                "name": name,
                "image": str(item.get("Image") or "unknown"),
                "state": state,
                "status": status,
                "network_mode": host_config.get("NetworkMode"),
                "ports": ", ".join(ports) or None,
                "health": health_match.group(1).lower() if health_match else None,
            }
        )
    return rows


def _socket_containers(socket_path: str) -> tuple[bool, list[dict[str, Any]], str | None]:
    path = Path(socket_path)
    if not path.exists():
        return False, [], "Configured Docker socket does not exist"

    connection = _UnixHTTPConnection(socket_path)
    try:
        connection.request(
            "GET",
            f"/containers/json?all=1&limit={MAX_CONTAINERS}",
            headers={"Host": "localhost", "User-Agent": "AuraLAN", "Connection": "close"},
        )
        response = connection.getresponse()
        payload = response.read(MAX_DOCKER_RESPONSE_BYTES + 1)
        if len(payload) > MAX_DOCKER_RESPONSE_BYTES:
            return True, [], "Docker response exceeded the AuraLAN size limit"
        if response.status != 200:
            return True, [], f"Docker Engine returned HTTP {response.status}"
        return True, parse_docker_list(payload.decode("utf-8", errors="replace")), None
    except (OSError, http.client.HTTPException) as exc:
        return True, [], f"Docker socket query failed: {type(exc).__name__}"
    finally:
        connection.close()


def _cli_containers() -> tuple[bool, list[dict[str, Any]], str | None]:
    if not command_exists("docker"):
        return False, [], None

    names = run_command(["docker", "ps", "-a", "--format", "{{.Names}}"], timeout=3.0)
    if names.code != 0:
        return True, [], names.error or names.output or "Docker could not be queried"
    container_names = [line.strip() for line in names.output.splitlines() if line.strip()][:MAX_CONTAINERS]
    if not container_names:
        return True, [], None

    inspected = run_command(["docker", "inspect", *container_names], timeout=4.0)
    if inspected.code != 0:
        return True, [], inspected.error or inspected.output or "Docker inspection failed"
    return True, parse_docker_inspect(inspected.output), None


def containers() -> tuple[bool, list[dict[str, Any]], str | None]:
    socket_path = os.environ.get("AURALAN_DOCKER_SOCKET", "").strip()
    if socket_path:
        return _socket_containers(socket_path)
    return _cli_containers()


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
