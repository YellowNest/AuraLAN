"""dnsmasq lease observations for the confirmed access-point scope."""

from __future__ import annotations

from typing import Any

from .base import DeviceObservation


def observations(entries: list[dict[str, Any]], access_point_interface: str | None) -> list[DeviceObservation]:
    result: list[DeviceObservation] = []
    for entry in entries:
        mac = entry.get("mac")
        if not mac:
            continue
        result.append(DeviceObservation(
            source="dhcp_lease", mac=str(mac), ip=entry.get("ip"), interface=access_point_interface,
            role="access_point" if access_point_interface else "unknown",
            hostname=entry.get("hostname"), lease_expires_at=entry.get("lease_expires_at"),
        ))
    return result
