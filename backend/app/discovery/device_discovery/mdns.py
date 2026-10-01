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
_cached: dict[tuple[str, str], tuple[float, str | None]] = {}


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

    target_keys = {(ip, mac) for ip, mac, _, _ in targets}
    now = time.monotonic()
    global _cached
    with _lock:
        # Keep only still-relevant, individually fresh entries. A single newly
        # observed device must not refresh the age of every older cache entry.
        _cached = {
            key: entry
            for key, entry in _cached.items()
            if key in target_keys and now - entry[0] < CACHE_TTL_SECONDS
        }
        cached = {key: entry[1] for key, entry in _cached.items()}

    missing = [target for target in targets if (target[0], target[1]) not in cached]
    if missing:
        resolved: dict[tuple[str, str], str | None] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="auralan-mdns") as executor:
            futures = {executor.submit(_resolve, ip): (ip, mac) for ip, mac, _, _ in missing}
            for future in concurrent.futures.as_completed(futures):
                key = futures[future]
                try:
                    resolved[key] = future.result()
                except Exception:
                    resolved[key] = None
        with _lock:
            # Cache misses too, but only for devices that are still in this
            # bounded observation set. This prevents long-running MAC churn from
            # turning the process cache into an ever-growing device history.
            for key, value in resolved.items():
                _cached[key] = (now, value)
            _cached = {key: entry for key, entry in _cached.items() if key in target_keys}
            cached = {key: entry[1] for key, entry in _cached.items()}

    return [
        DeviceObservation(source="mdns_name", mac=mac, ip=ip, interface=interface, role=role, hostname=cached[(ip, mac)])
        for ip, mac, interface, role in targets if cached.get((ip, mac))
    ]
