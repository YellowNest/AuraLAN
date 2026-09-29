"""Passive `ip neigh` observations."""

from __future__ import annotations

from typing import Any

from ..command import command_exists, run_command
from .base import DeviceObservation


def rows() -> list[dict[str, str]]:
    if not command_exists("ip"):
        return []
    result = run_command(["ip", "neigh", "show"], timeout=1.5)
    if result.code != 0:
        return []
    parsed: list[dict[str, str]] = []
    for line in result.output.splitlines():
        tokens = line.split()
        if "dev" not in tokens or "lladdr" not in tokens:
            continue
        try:
            parsed.append({
                "ip": tokens[0],
                "interface": tokens[tokens.index("dev") + 1],
                "mac": tokens[tokens.index("lladdr") + 1].upper(),
                "state": tokens[-1].upper(),
            })
        except IndexError:
            continue
    return parsed


def observations(interface_roles: dict[str, str], source_rows: list[dict[str, str]] | None = None) -> list[DeviceObservation]:
    records = rows() if source_rows is None else source_rows
    excluded = {"container_bridge", "virtual", "vpn"}
    result: list[DeviceObservation] = []
    for row in records:
        role = interface_roles.get(row.get("interface", ""), "unknown")
        if role in excluded:
            continue
        mac = row.get("mac")
        if not mac:
            continue
        result.append(DeviceObservation(
            source="ip_neigh", mac=mac, ip=row.get("ip"), interface=row.get("interface"),
            role=role, neighbour_state=row.get("state"),
        ))
    return result
