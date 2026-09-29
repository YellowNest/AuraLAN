"""Opt-in Wake-on-LAN support for known AuraLAN devices."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import dataclass

TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_BROADCAST = "255.255.255.255"
DEFAULT_PORT = 9


@dataclass(frozen=True)
class WakeConfig:
    enabled: bool
    broadcast: str
    port: int


def wake_config() -> WakeConfig:
    enabled = os.environ.get("AURALAN_ENABLE_WAKE_ON_LAN", "").strip().lower() in TRUE_VALUES

    raw_broadcast = os.environ.get("AURALAN_WAKE_BROADCAST", DEFAULT_BROADCAST).strip()
    try:
        broadcast = str(ipaddress.IPv4Address(raw_broadcast))
    except ipaddress.AddressValueError:
        broadcast = DEFAULT_BROADCAST

    raw_port = os.environ.get("AURALAN_WAKE_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = DEFAULT_PORT
    if not 1 <= port <= 65535:
        port = DEFAULT_PORT

    return WakeConfig(enabled=enabled, broadcast=broadcast, port=port)


def normalize_mac(value: str | None) -> str | None:
    compact = re.sub(r"[^0-9A-Fa-f]", "", str(value or ""))
    if len(compact) != 12 or not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        return None
    first_octet = int(compact[:2], 16)
    if first_octet & 0x01:
        return None
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2)).upper()


def is_globally_administered(mac: str) -> bool:
    first_octet = int(mac[:2], 16)
    return not bool(first_octet & 0x02)


def select_wake_mac(device: dict) -> str | None:
    candidates: list[str] = []
    for value in [*(device.get("mac_addresses") or []), device.get("mac")]:
        normalized = normalize_mac(value)
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    if not candidates:
        return None
    return next((mac for mac in candidates if is_globally_administered(mac)), candidates[0])


def magic_packet(mac: str) -> bytes:
    normalized = normalize_mac(mac)
    if not normalized:
        raise ValueError("Invalid unicast MAC address")
    raw = bytes.fromhex(normalized.replace(":", ""))
    return b"\xff" * 6 + raw * 16


def send_magic_packet(mac: str, config: WakeConfig | None = None) -> WakeConfig:
    active = config or wake_config()
    if not active.enabled:
        raise PermissionError("Wake-on-LAN is disabled")
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.0)
        sock.sendto(packet, (active.broadcast, active.port))
    return active
