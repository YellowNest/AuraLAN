"""Bounded SSDP/UPnP friendly-name enrichment for known LAN clients.

AuraLAN sends one standard SSDP discovery request, but only accepts responses
from IP addresses that are already present in its neighbour/DHCP evidence.
UPnP device descriptions are fetched only from the responding IP itself, over
plain local HTTP, with strict time and size limits.
"""

from __future__ import annotations

import concurrent.futures
import http.client
import ipaddress
import socket
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET

from .base import DeviceObservation

CACHE_TTL_SECONDS = 180.0
DISCOVERY_WINDOW_SECONDS = 1.0
MAX_RESPONSES = 64
MAX_DESCRIPTION_BYTES = 131072
MAX_WORKERS = 6
SSDP_ADDRESS = ("239.255.255.250", 1900)

_lock = threading.Lock()
_cached_at = 0.0
_cached_rows: list[dict[str, str | None]] = []


def _parse_headers(payload: bytes) -> dict[str, str]:
    try:
        text = payload.decode("utf-8", errors="ignore")
    except Exception:
        return {}
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or "200" not in lines[0]:
        return {}
    headers: dict[str, str] = {}
    for line in lines[1:]:
        key, separator, value = line.partition(":")
        if separator and key.strip() and value.strip():
            headers[key.strip().lower()] = value.strip()
    return headers


def _local_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and not address.is_loopback and not address.is_multicast and not address.is_unspecified


def _safe_location(location: str, source_ip: str) -> tuple[int, str] | None:
    try:
        parsed = urllib.parse.urlsplit(location)
    except ValueError:
        return None
    if parsed.scheme.lower() != "http" or not parsed.hostname:
        return None
    if parsed.hostname != source_ip or not _local_ipv4(source_ip):
        return None
    try:
        port = parsed.port or 80
    except ValueError:
        return None
    if not (1 <= port <= 65535):
        return None
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    if len(path) > 2048:
        return None
    return port, path


def _parse_description(xml_bytes: bytes) -> dict[str, str | None]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}

    values: dict[str, str | None] = {
        "friendly_name": None,
        "manufacturer": None,
        "model": None,
        "device_type": None,
    }
    wanted = {
        "friendlyname": "friendly_name",
        "manufacturer": "manufacturer",
        "modelname": "model",
        "devicetype": "device_type",
    }
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        target = wanted.get(tag)
        if not target or values[target]:
            continue
        value = (node.text or "").strip()
        if value and len(value) <= 160:
            values[target] = value
    return values


def _fetch_description(source_ip: str, location: str) -> dict[str, str | None]:
    safe = _safe_location(location, source_ip)
    if safe is None:
        return {}
    port, path = safe
    connection = http.client.HTTPConnection(source_ip, port, timeout=0.8)
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Host": source_ip,
                "Accept": "text/xml, application/xml",
                "Connection": "close",
                "User-Agent": "AuraLAN",
            },
        )
        response = connection.getresponse()
        if response.status < 200 or response.status >= 300:
            return {}
        body = response.read(MAX_DESCRIPTION_BYTES + 1)
        if len(body) > MAX_DESCRIPTION_BYTES:
            return {}
        return _parse_description(body)
    except (OSError, http.client.HTTPException):
        return {}
    finally:
        connection.close()


def _discover_locations(known_ips: set[str]) -> list[tuple[str, str, str | None]]:
    if not known_ips:
        return []
    request = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 1\r\n"
        "ST: ssdp:all\r\n\r\n"
    ).encode("ascii")

    found: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.settimeout(0.15)
        sock.sendto(request, SSDP_ADDRESS)
        deadline = time.monotonic() + DISCOVERY_WINDOW_SECONDS
        while time.monotonic() < deadline and len(found) < MAX_RESPONSES:
            try:
                payload, address = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            source_ip = address[0]
            if source_ip not in known_ips:
                continue
            headers = _parse_headers(payload)
            location = headers.get("location")
            if not location or _safe_location(location, source_ip) is None:
                continue
            key = (source_ip, location)
            if key in seen:
                continue
            seen.add(key)
            found.append((source_ip, location, headers.get("st") or headers.get("nt")))
    except OSError:
        return []
    finally:
        sock.close()
    return found


def _discover_rows(known_ips: set[str]) -> list[dict[str, str | None]]:
    locations = _discover_locations(known_ips)
    if not locations:
        return []

    rows: list[dict[str, str | None]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="auralan-ssdp") as executor:
        futures = {
            executor.submit(_fetch_description, ip, location): (ip, service_type)
            for ip, location, service_type in locations
        }
        for future in concurrent.futures.as_completed(futures):
            ip, response_type = futures[future]
            try:
                description = future.result()
            except Exception:
                description = {}
            if not description:
                continue
            rows.append({
                "ip": ip,
                "friendly_name": description.get("friendly_name"),
                "manufacturer": description.get("manufacturer"),
                "model": description.get("model"),
                "device_type": description.get("device_type") or response_type,
            })
    return rows


def _rows(known_ips: set[str]) -> list[dict[str, str | None]]:
    global _cached_at, _cached_rows
    now = time.monotonic()
    with _lock:
        if now - _cached_at < CACHE_TTL_SECONDS:
            return [row for row in _cached_rows if row.get("ip") in known_ips]

    rows = _discover_rows(known_ips)
    with _lock:
        _cached_rows = rows
        _cached_at = now
        return list(_cached_rows)


def observations(seed: list[DeviceObservation]) -> list[DeviceObservation]:
    by_ip: dict[str, DeviceObservation] = {}
    for item in seed:
        if item.ip and item.ip not in by_ip:
            by_ip[item.ip] = item
    known_ips = {ip for ip in by_ip if _local_ipv4(ip)}
    if not known_ips:
        return []

    result: list[DeviceObservation] = []
    for row in _rows(known_ips):
        ip = str(row.get("ip") or "")
        base = by_ip.get(ip)
        if base is None:
            continue
        friendly_name = str(row.get("friendly_name") or "").strip() or None
        manufacturer = str(row.get("manufacturer") or "").strip() or None
        model = str(row.get("model") or "").strip() or None
        device_type = str(row.get("device_type") or "").strip() or None
        if not any((friendly_name, manufacturer, model, device_type)):
            continue
        result.append(DeviceObservation(
            source="ssdp",
            mac=base.mac,
            ip=ip,
            interface=base.interface,
            role=base.role,
            service_name=friendly_name,
            service_types=(device_type,) if device_type else (),
            model=model,
            manufacturer=manufacturer,
        ))
    return result
