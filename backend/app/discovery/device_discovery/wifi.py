"""Associated AP stations are strong, passive online evidence."""

from __future__ import annotations

from .base import DeviceObservation


def observations(signals: dict[str, int], access_point_interface: str | None) -> list[DeviceObservation]:
    return [DeviceObservation(
        source="wifi_station", mac=mac, interface=access_point_interface, role="access_point", signal_dbm=signal,
    ) for mac, signal in signals.items()]
