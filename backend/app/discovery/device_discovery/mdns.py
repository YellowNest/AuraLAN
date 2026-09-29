"""Bounded mDNS name enrichment for already-known local neighbours.

This is not a scan: it only asks the local Avahi resolver about addresses that
`ip neigh` already exposed, caches both hits and misses, and is optional.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time

from ..command import command_exists, run_command
from .base import DeviceObservation

CACHE_TTL_SECONDS = 300.0
MAX_ADDRESSES = 32
MAX_WORKERS = 6
_lock = threading.Lock()
_cached_at = 0.0
_cached: dict[tuple[str, str], str | None] = {}


def _resolve(ip: str) -> str | None:
    result = run_command(["avahi-resolve-address", "-4", ip], timeout=0.7)
    if result.code != 0 or not result.output:
        return None
    fields = result.output.split()
    if len(fields) < 2:
        return None
    hostname = fields[-1].removesuffix(".local")
    return hostname if hostname and hostname != ip else None


def observations(seed: list[DeviceObservation]) -> list[DeviceObservation]:
    if not command_exists("avahi-resolve-address"):
        return []
    targets = [(item.ip, item.mac, item.interface, item.role) for item in seed if item.source == "ip_neigh" and item.ip]
    targets = targets[:MAX_ADDRESSES]
    if not targets:
        return []
    global _cached_at, _cached
    now = time.monotonic()
    with _lock:
        cached = dict(_cached) if now - _cached_at < CACHE_TTL_SECONDS else {}
    missing = [target for target in targets if (target[0], target[1]) not in cached]
    if missing:
        resolved: dict[tuple[str, str], str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="auralan-mdns") as executor:
            futures = {executor.submit(_resolve, ip): (ip, mac) for ip, mac, _, _ in missing}
            for future in concurrent.futures.as_completed(futures):
                name = future.result()
                if name:
                    resolved[futures[future]] = name
        with _lock:
            # Cache misses as None too: otherwise a quiet LAN would spawn the
            # same Avahi subprocesses on every two-second dashboard snapshot.
            _cached = {**cached, **{(ip, mac): resolved.get((ip, mac)) for ip, mac, _, _ in missing}}
            _cached_at = now
            cached = dict(_cached)
    return [
        DeviceObservation(source="mdns_name", mac=mac, ip=ip, interface=interface, role=role, hostname=cached[(ip, mac)])
        for ip, mac, interface, role in targets if cached.get((ip, mac))
    ]
