"""Opt-in, bounded TCP availability for locally observed RFC1918 devices.

No hostname resolution, subnet enumeration, banner reads or cloud access.
Targets are explicitly configured and only probed when present in the latest
discovery inventory. Unobserved targets are *not* called offline.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

MAX_CHECKS = 12
CONNECT_TIMEOUT = 0.4
def _private_lan(ip: ipaddress.IPv4Address) -> bool:
    a, b = ip.packed[:2]
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)


@dataclass(frozen=True)
class ServiceTarget:
    name: str
    ip: str
    port: int


def configured_targets(raw: str | None = None) -> tuple[ServiceTarget, ...]:
    value = os.environ.get("AURALAN_TCP_CHECKS", "") if raw is None else raw
    if not isinstance(value, str) or len(value) > 4096:
        return ()
    try:
        items = json.loads(value) if value.strip() else []
    except (TypeError, ValueError):
        return ()
    if not isinstance(items, list) or len(items) > MAX_CHECKS:
        return ()
    valid: list[ServiceTarget] = []
    identities: set[tuple[str, int]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        ip = item.get("ip")
        port = item.get("port")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48:
            continue
        if not isinstance(ip, str) or len(ip) > 15:
            continue
        try:
            parsed_ip = ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError:
            continue
        if not _private_lan(parsed_ip):
            continue
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            continue
        identity = (str(parsed_ip), port)
        if identity in identities:
            continue
        identities.add(identity)
        valid.append(ServiceTarget(name=name.strip(), ip=str(parsed_ip), port=port))
    return tuple(valid)


def tcp_open(ip: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(CONNECT_TIMEOUT)
            return connection.connect_ex((ip, port)) == 0
    except OSError:
        return False


class LocalServiceChecks:
    """Snapshot-driven checks; bounded threads and atomic status publication."""

    def __init__(self, targets: tuple[ServiceTarget, ...] | None = None) -> None:
        self.targets = configured_targets() if targets is None else tuple(targets)
        self._lock = threading.Lock()
        self._items: list[dict[str, Any]] = [
            {"name": item.name, "ip": item.ip, "port": item.port, "state": "unknown", "checked_at": None}
            for item in self.targets
        ]

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"configured": bool(self.targets), "items": [dict(item) for item in self._items]}

    def update(self, snapshot: dict[str, Any]) -> None:
        if not self.targets:
            return
        observed: set[str] = set()
        for device in snapshot.get("devices", []):
            if not isinstance(device, dict) or device.get("state") in ("known", "offline"):
                continue
            addresses = [device.get("ip"), *(device.get("ip_addresses") or [])]
            for value in addresses:
                if isinstance(value, str):
                    observed.add(value)
        candidates = [(i, item) for i, item in enumerate(self.targets) if item.ip in observed]
        checked: dict[int, bool] = {}
        if candidates:
            with ThreadPoolExecutor(max_workers=min(4, len(candidates)), thread_name_prefix="auralan-tcp-watch") as executor:
                submitted = {executor.submit(tcp_open, item.ip, item.port): i for i, item in candidates}
                for future, index in submitted.items():
                    try:
                        checked[index] = bool(future.result())
                    except Exception:
                        checked[index] = False

        now = int(time.time())
        items = [
            {
                "name": item.name, "ip": item.ip, "port": item.port,
                "state": ("online" if checked[index] else "offline") if index in checked else "unknown",
                "checked_at": now if index in checked else None,
            }
            for index, item in enumerate(self.targets)
        ]
        with self._lock:
            self._items = items
