"""Provider-neutral evidence used by the device identity resolver."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceObservation:
    """A single passive fact about a network client; it is not a device yet."""

    source: str
    mac: str
    ip: str | None = None
    interface: str | None = None
    role: str = "unknown"
    neighbour_state: str | None = None
    hostname: str | None = None
    signal_dbm: int | None = None
    lease_expires_at: int | None = None
    service_name: str | None = None
    service_types: tuple[str, ...] = ()
    profile_hints: tuple[str, ...] = ()
    model: str | None = None
    manufacturer: str | None = None

    @property
    def normalized_mac(self) -> str:
        return self.mac.upper()
