"""Local host-file name enrichment for already-known devices.

Only local files are read. No DNS query, cloud lookup, or address-space scan is
performed, so private network identifiers never leave the host.
"""

from __future__ import annotations

import ipaddress
import threading
import time
from pathlib import Path

from .base import DeviceObservation

CACHE_TTL_SECONDS = 60.0
HOST_FILES = (
    Path("/etc/hosts"),
    Path("/etc/pihole/hosts/custom.list"),
    Path("/etc/pihole/custom.list"),
)

_lock = threading.Lock()
_cached_at = 0.0
_cached_names: dict[str, str] = {}


def _valid_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and not address.is_loopback and not address.is_multicast and not address.is_unspecified


def _read_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for path in HOST_FILES:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            fields = line.split()
            if len(fields) < 2 or not _valid_ipv4(fields[0]):
                continue
            hostname = next((name for name in fields[1:] if name and name != "localhost"), None)
            if hostname:
                names.setdefault(fields[0], hostname.rstrip(".").removesuffix(".local"))
    return names


def _names() -> dict[str, str]:
    global _cached_at, _cached_names
    now = time.monotonic()
    with _lock:
        if now - _cached_at < CACHE_TTL_SECONDS:
            return dict(_cached_names)
    names = _read_names()
    with _lock:
        _cached_names = names
        _cached_at = now
        return dict(_cached_names)


def observations(seed: list[DeviceObservation]) -> list[DeviceObservation]:
    names = _names()
    if not names:
        return []

    result: list[DeviceObservation] = []
    seen: set[tuple[str, str]] = set()
    for item in seed:
        if not item.ip or item.ip not in names:
            continue
        key = (item.ip, item.mac)
        if key in seen:
            continue
        seen.add(key)
        result.append(DeviceObservation(
            source="local_hosts",
            mac=item.mac,
            ip=item.ip,
            interface=item.interface,
            role=item.role,
            hostname=names[item.ip],
        ))
    return result
