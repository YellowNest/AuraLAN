"""Bounded, on-demand common TCP service checks for known AuraLAN devices.

AuraLAN intentionally does not scan address ranges. A service check is only
started for a device AuraLAN already knows, uses one of that device's observed
IPv4 addresses, probes a small fixed list of common TCP ports, and never reads
application banners.
"""

from __future__ import annotations

import concurrent.futures
import socket
import time
from typing import Iterable

from .probe import select_probe_ip

CONNECT_TIMEOUT_SECONDS = 0.35
MAX_WORKERS = 16

COMMON_TCP_SERVICES: tuple[tuple[int, str], ...] = (
    (21, "FTP"),
    (22, "SSH"),
    (23, "Telnet"),
    (25, "SMTP"),
    (53, "DNS"),
    (80, "HTTP"),
    (139, "NetBIOS"),
    (443, "HTTPS"),
    (445, "SMB"),
    (548, "AFP"),
    (554, "RTSP"),
    (631, "IPP"),
    (1883, "MQTT"),
    (3000, "Web app"),
    (3389, "RDP"),
    (5000, "Web app"),
    (5357, "WSD"),
    (8000, "HTTP alt"),
    (8008, "Cast"),
    (8009, "Cast"),
    (8080, "HTTP alt"),
    (8123, "Home Assistant"),
    (8443, "HTTPS alt"),
    (8883, "MQTT TLS"),
    (9100, "JetDirect"),
    (32400, "Plex"),
)
SERVICE_NAMES = dict(COMMON_TCP_SERVICES)


def service_label(port: int) -> str:
    return SERVICE_NAMES.get(int(port), "TCP")


def _check_port(target: str, port: int, timeout: float) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        return sock.connect_ex((target, int(port))) == 0
    except OSError:
        return False
    finally:
        sock.close()


def scan_ports(
    target: str,
    ports: Iterable[int] | None = None,
    *,
    timeout: float = CONNECT_TIMEOUT_SECONDS,
) -> list[int]:
    """Return open TCP ports from a bounded, fixed-target connect check."""
    requested = tuple(dict.fromkeys(
        int(port)
        for port in (ports if ports is not None else SERVICE_NAMES)
        if 1 <= int(port) <= 65535
    ))
    if not requested:
        return []

    workers = min(MAX_WORKERS, len(requested))
    open_ports: list[int] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="auralan-service-check",
    ) as executor:
        futures = {
            executor.submit(_check_port, target, port, timeout): port
            for port in requested
        }
        for future in concurrent.futures.as_completed(futures):
            port = futures[future]
            try:
                if future.result():
                    open_ports.append(port)
            except Exception:
                # One failed connect attempt must not abort the whole check.
                continue
    return sorted(open_ports)


def scan_device_services(device: dict) -> dict:
    target = select_probe_ip(device)
    if not target:
        raise ValueError("Device has no usable IPv4 address for a local service check")

    open_ports = scan_ports(target)
    return {
        "device_id": str(device.get("id") or ""),
        "ip": target,
        "open_ports": open_ports,
        "checked_at": int(time.time()),
    }
