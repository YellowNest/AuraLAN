"""Bounded hostname enrichment through the host's configured resolver.

Only addresses AuraLAN already observed are queried. This is not an address-space
scan. Hits and misses are cached to keep periodic refreshes cheap.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import threading
import time

from ..command import command_exists, run_command
from .base import DeviceObservation

CACHE_TTL_SECONDS = 300.0
MAX_ADDRESSES = 32
MAX_WORKERS = 6

_lock = threading.Lock()
_cached_at = 0.0
_cached: dict[str, str | None] = {}


def _clean_name(value: str, ip: str) -> str | None:
    name = (value or "").strip().rstrip(".").removesuffix(".local")
    if not name or name == ip or name.lower() == "localhost":
        return None
    try:
        ipaddress.ip_address(name)
        return None
    except ValueError:
        pass
    if len(name) > 120 or any(character.isspace() for character in name):
        return None
    return name


def _resolve(ip: str) -> str | None:
    result = run_command(["getent", "hosts", ip], timeout=0.7)
    if result.code != 0 or not result.output:
        return None
    for line in result.output.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        for candidate in fields[1:]:
            cleaned = _clean_name(candidate, ip)
            if cleaned:
                return cleaned
    return None


def observations(seed: list[DeviceObservation]) -> list[DeviceObservation]:
    if not command_exists("getent"):
        return []

    bases: dict[str, DeviceObservation] = {}
    for item in seed:
        if item.ip and item.ip not in bases:
            bases[item.ip] = item
        if len(bases) >= MAX_ADDRESSES:
            break
    if not bases:
        return []

    global _cached_at, _cached
    now = time.monotonic()
    with _lock:
        cached = dict(_cached) if now - _cached_at < CACHE_TTL_SECONDS else {}

    missing = [ip for ip in bases if ip not in cached]
    if missing:
        resolved: dict[str, str | None] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="auralan-resolver") as executor:
            futures = {executor.submit(_resolve, ip): ip for ip in missing}
            for future in concurrent.futures.as_completed(futures):
                ip = futures[future]
                try:
                    resolved[ip] = future.result()
                except Exception:
                    resolved[ip] = None
        with _lock:
            _cached = {**cached, **resolved}
            _cached_at = now
            cached = dict(_cached)

    return [
        DeviceObservation(
            source="local_resolver",
            mac=base.mac,
            ip=ip,
            interface=base.interface,
            role=base.role,
            hostname=cached[ip],
        )
        for ip, base in bases.items()
        if cached.get(ip)
    ]
