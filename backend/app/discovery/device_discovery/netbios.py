"""Bounded NetBIOS name enrichment for already-known IPv4 clients."""

from __future__ import annotations

import concurrent.futures
import re
import threading
import time

from ..command import command_exists, run_command
from .base import DeviceObservation

CACHE_TTL_SECONDS = 300.0
MAX_ADDRESSES = 32
MAX_WORKERS = 6
MAX_CACHE_ENTRIES = 128

_lock = threading.Lock()
_cached: dict[str, tuple[float, str | None]] = {}


def _parse_name(output: str) -> str | None:
    for raw in (output or "").splitlines():
        if "<00>" not in raw or "<GROUP>" in raw:
            continue
        match = re.match(r"\s*([^\s<]{1,63})\s+<00>\s+-", raw)
        if not match:
            continue
        value = match.group(1).strip()
        if value and value != "__MSBROWSE__":
            return value
    return None


def _resolve(ip: str) -> str | None:
    result = run_command(["nmblookup", "-A", ip], timeout=0.8)
    if result.code != 0:
        return None
    return _parse_name(result.output)


def observations(seed: list[DeviceObservation]) -> list[DeviceObservation]:
    if not command_exists("nmblookup"):
        return []

    bases: dict[str, DeviceObservation] = {}
    for item in seed:
        if item.ip and item.ip not in bases:
            bases[item.ip] = item
        if len(bases) >= MAX_ADDRESSES:
            break
    if not bases:
        return []

    now = time.monotonic()
    global _cached
    with _lock:
        _cached = {
            ip: entry
            for ip, entry in _cached.items()
            if now - entry[0] < CACHE_TTL_SECONDS
        }
        if len(_cached) > MAX_CACHE_ENTRIES:
            newest = sorted(_cached.items(), key=lambda item: item[1][0], reverse=True)[:MAX_CACHE_ENTRIES]
            _cached = dict(newest)
        cached = {ip: entry[1] for ip, entry in _cached.items()}

    missing = [ip for ip in bases if ip not in cached]
    if missing:
        resolved: dict[str, str | None] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="auralan-netbios") as executor:
            futures = {executor.submit(_resolve, ip): ip for ip in missing}
            for future in concurrent.futures.as_completed(futures):
                ip = futures[future]
                try:
                    resolved[ip] = future.result()
                except Exception:
                    resolved[ip] = None
        with _lock:
            for ip, value in resolved.items():
                _cached[ip] = (now, value)
            if len(_cached) > MAX_CACHE_ENTRIES:
                newest = sorted(_cached.items(), key=lambda item: item[1][0], reverse=True)[:MAX_CACHE_ENTRIES]
                _cached = dict(newest)
            cached = {ip: entry[1] for ip, entry in _cached.items()}

    return [
        DeviceObservation(
            source="netbios_name",
            mac=base.mac,
            ip=ip,
            interface=base.interface,
            role=base.role,
            hostname=cached[ip],
        )
        for ip, base in bases.items()
        if cached.get(ip)
    ]
