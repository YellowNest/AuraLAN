"""Bounded, on-demand ICMP reachability checks for known AuraLAN devices."""

from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
import time

_LATENCY_RE = re.compile(r"\\btime[=<]\\s*(\\d+(?:\\.\\d+)?)\\s*ms\\b", re.IGNORECASE)


class ProbeUnavailable(RuntimeError):
    """Raised when the host cannot perform the bounded ICMP probe."""


def probe_available() -> bool:
    return shutil.which("ping") is not None


def select_probe_ip(device: dict) -> str | None:
    candidates = [*(device.get("ip_addresses") or []), device.get("ip")]
    seen: set[str] = set()

    for raw in candidates:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if not isinstance(address, ipaddress.IPv4Address):
            continue
        if address.is_unspecified or address.is_multicast or address.is_loopback:
            continue
        if address == ipaddress.IPv4Address("255.255.255.255"):
            continue
        return str(address)

    return None


def _latency_ms(output: str) -> float | None:
    match = _LATENCY_RE.search(output or "")
    if not match:
        return None
    try:
        return round(float(match.group(1)), 3)
    except ValueError:
        return None


def probe_device(device: dict) -> dict:
    binary = shutil.which("ping")
    if not binary:
        raise ProbeUnavailable("ping utility is not installed")

    target = select_probe_ip(device)
    if not target:
        raise ValueError("Device has no usable IPv4 address for an ICMP reachability check")

    try:
        completed = subprocess.run(
            [binary, "-n", "-c", "1", "-W", "1", target],
            capture_output=True,
            text=True,
            timeout=2.5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        completed = None
    except OSError as exc:
        raise ProbeUnavailable("ping utility could not be executed") from exc

    reply_received = completed is not None and completed.returncode == 0
    output = completed.stdout if completed is not None else ""

    return {
        "device_id": str(device.get("id") or ""),
        "ip": target,
        "reply_received": reply_received,
        "latency_ms": _latency_ms(output) if reply_received else None,
        "checked_at": int(time.time()),
    }
