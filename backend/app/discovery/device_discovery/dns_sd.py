"""DNS-SD/mDNS service enrichment for devices AuraLAN already knows.

A single bounded Avahi browse can reveal useful local names and service types
(AirPlay, printers, Cast, HomeKit, etc.) without scanning address space or
sending device identity data outside the LAN.
"""

from __future__ import annotations

import re
import threading
import time

from ..command import command_exists, run_command
from .base import DeviceObservation

CACHE_TTL_SECONDS = 120.0
MAX_CACHE_ROWS = 512
MAX_VALUES_PER_DEVICE = 32

HOMEKIT_CATEGORY_HINTS = {
    "2": "homekit-bridge",
    "3": "homekit-fan",
    "4": "homekit-garage-door",
    "5": "homekit-light",
    "6": "homekit-lock",
    "7": "homekit-outlet",
    "8": "homekit-switch",
    "9": "homekit-thermostat",
    "10": "homekit-sensor",
    "11": "homekit-security-system",
    "12": "homekit-door",
    "13": "homekit-window",
    "14": "homekit-window-covering",
    "15": "homekit-programmable-switch",
    "17": "homekit-camera",
    "18": "homekit-video-doorbell",
    "19": "homekit-air-purifier",
    "20": "homekit-heater",
    "21": "homekit-air-conditioner",
    "22": "homekit-humidifier",
    "23": "homekit-dehumidifier",
    "28": "homekit-sprinkler",
    "29": "homekit-faucet",
    "30": "homekit-shower-system",
    "31": "homekit-television",
    "33": "homekit-router",
    "34": "homekit-audio-receiver",
}

HUMAN_NAME_SERVICE_TYPES = {
    "_airplay._tcp",
    "_raop._tcp",
    "_companion-link._tcp",
}
_lock = threading.Lock()
_cached_at = 0.0
_cached_rows: list[tuple[str, str, str, str, str, str | None, str | None, str | None, tuple[str, ...]]] = []


def _unescape(value: str) -> str:
    """Decode standard DNS-SD escaping into a UTF-8 string."""
    source = value or ""
    payload = bytearray()
    index = 0
    while index < len(source):
        if source[index] == "\\" and index + 1 < len(source):
            if index + 3 < len(source) and source[index + 1:index + 4].isdigit():
                payload.append(int(source[index + 1:index + 4], 10))
                index += 4
                continue
            # DNS escaping uses a backslash before a literal punctuation
            # character too, e.g. "\\." means a literal dot.
            payload.extend(source[index + 1].encode("utf-8", errors="replace"))
            index += 2
            continue
        payload.extend(source[index].encode("utf-8", errors="replace"))
        index += 1
    return payload.decode("utf-8", errors="replace").strip().strip('"')

def _browse_rows() -> list[tuple[str, str, str, str, str, str | None, str | None, str | None, tuple[str, ...]]]:
    result = run_command(
        ["avahi-browse", "--all", "--resolve", "--terminate", "--parsable", "--no-db-lookup"],
        timeout=2.2,
    )
    if result.code != 0 or not result.output:
        return []

    rows: list[tuple[str, str, str, str, str, str | None, str | None, str | None, tuple[str, ...]]] = []
    model_keys = {"model", "modelname", "md", "rpmd", "ty", "am", "product"}
    manufacturer_keys = {"manufacturer", "mf", "vendor"}
    friendly_name_keys = {"fn", "name", "device_name"}

    for raw in result.output.splitlines():
        fields = raw.split(";")
        if len(fields) < 9 or fields[0] != "=" or fields[2] != "IPv4":
            continue
        interface = _unescape(fields[1])
        service_name = _unescape(fields[3])
        service_type = _unescape(fields[4]).lower()
        hostname = _unescape(fields[6]).rstrip(".").removesuffix(".local")
        ip = _unescape(fields[7])
        if not ip:
            continue

        model = None
        manufacturer = None
        friendly_name = None
        profile_hints: list[str] = []
        txt_blob = ";".join(fields[9:]) if len(fields) > 9 else ""
        for raw_txt in re.findall(r'"([^"]*)"', txt_blob):
            txt = _unescape(raw_txt)
            key, separator, value = txt.partition("=")
            if not separator:
                continue
            key = key.strip().lower()
            value = value.strip()
            if not value or len(value) > 120:
                continue
            if key in model_keys and model is None:
                model = value
            elif key in manufacturer_keys and manufacturer is None:
                manufacturer = value
            elif key in friendly_name_keys and friendly_name is None:
                friendly_name = value
            elif key == "ci" and service_type in {"_hap._tcp", "_homekit._tcp"}:
                hint = HOMEKIT_CATEGORY_HINTS.get(value)
                if hint and hint not in profile_hints:
                    profile_hints.append(hint)

        rows.append((ip, interface, service_name, service_type, hostname, model, manufacturer, friendly_name, tuple(profile_hints)))
        if len(rows) >= MAX_CACHE_ROWS:
            break
    return rows


def _cached_browse_rows() -> list[tuple[str, str, str, str, str, str | None, str | None, str | None, tuple[str, ...]]]:
    global _cached_at, _cached_rows
    now = time.monotonic()
    with _lock:
        if now - _cached_at < CACHE_TTL_SECONDS:
            return list(_cached_rows)

    rows = _browse_rows()
    with _lock:
        _cached_rows = rows
        _cached_at = now
        return list(_cached_rows)


def _useful_service_name(name: str, hostname: str) -> str | None:
    value = re.sub(r"\s+\[[0-9A-Fa-f:.-]{11,}\]$", "", name.strip()).strip()
    if not value:
        return None

    # Several Bonjour implementations prefix a human label with a stable
    # hexadecimal instance identifier. Preserve the useful suffix, never the
    # deployment-specific identifier.
    identifier = re.match(
        r"^(?:[0-9A-Fa-f]{12}|(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})@(.+)$",
        value,
    )
    if identifier:
        value = identifier.group(1).strip()

    # Reject protocol/capability strings masquerading as a service name.
    if re.search(r"(?:^|@)fe80::|supportsRP-\d+$", value, re.IGNORECASE):
        return None
    normalized = re.sub(r"[-_.\s]+", "", value).lower()
    host_normalized = re.sub(r"[-_.\s]+", "", hostname).lower()
    if normalized and normalized == host_normalized:
        return None
    if re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value, re.IGNORECASE):
        return None
    if re.fullmatch(r"[0-9a-f]{12,}", normalized, re.IGNORECASE):
        return None
    if value.lower() in {"airplay", "google cast", "spotify connect", "homekit", "workstation"}:
        return None
    return value


def _sleep_proxy_name(name: str, hostname: str) -> str | None:
    """Extract the human label from Apple's Sleep Proxy instance convention."""
    value = (name or "").strip()
    match = re.match(r"^(?:[0-9A-Fa-f]{2}-){3}[0-9A-Fa-f]{2}\.\d+\s+(.+)$", value)
    if not match:
        return None
    return _useful_service_name(match.group(1), hostname)


def observations(seed: list[DeviceObservation]) -> list[DeviceObservation]:
    if not command_exists("avahi-browse"):
        return []

    by_ip: dict[str, DeviceObservation] = {}
    for item in seed:
        if item.ip and item.ip not in by_ip:
            by_ip[item.ip] = item
    if not by_ip:
        return []

    grouped: dict[str, dict[str, object]] = {}
    for ip, interface, service_name, service_type, hostname, model, manufacturer, friendly_name, profile_hints in _cached_browse_rows():
        base = by_ip.get(ip)
        if base is None:
            continue
        row = grouped.setdefault(ip, {
            "base": base,
            "hostname": hostname or None,
            "service_names": [],
            "service_types": [],
            "models": [],
            "manufacturers": [],
            "profile_hints": [],
            "interface": interface or base.interface,
        })
        if hostname and not row["hostname"]:
            row["hostname"] = hostname
        if service_type and service_type not in row["service_types"] and len(row["service_types"]) < MAX_VALUES_PER_DEVICE:
            row["service_types"].append(service_type)
        if service_type == "_sleep-proxy._udp":
            # Apple's Sleep Proxy instance convention can carry a useful human
            # label after an implementation prefix. Keep only that label.
            sleep_name = _sleep_proxy_name(service_name, hostname)
            if sleep_name and sleep_name not in row["service_names"] and len(row["service_names"]) < MAX_VALUES_PER_DEVICE:
                row["service_names"].insert(0, sleep_name)
        else:
            service_hostname = "" if service_type in HUMAN_NAME_SERVICE_TYPES else hostname
            for candidate, comparison_hostname in ((friendly_name, ""), (service_name, service_hostname)):
                useful_name = _useful_service_name(candidate or "", comparison_hostname)
                if useful_name and useful_name not in row["service_names"] and len(row["service_names"]) < MAX_VALUES_PER_DEVICE:
                    row["service_names"].append(useful_name)
        if model and model not in row["models"] and len(row["models"]) < MAX_VALUES_PER_DEVICE:
            row["models"].append(model)
        if manufacturer and manufacturer not in row["manufacturers"] and len(row["manufacturers"]) < MAX_VALUES_PER_DEVICE:
            row["manufacturers"].append(manufacturer)
        for hint in profile_hints:
            if hint not in row["profile_hints"] and len(row["profile_hints"]) < MAX_VALUES_PER_DEVICE:
                row["profile_hints"].append(hint)

    result: list[DeviceObservation] = []
    for ip, row in grouped.items():
        base = row["base"]
        service_names = row["service_names"]
        service_name = service_names[0] if service_names else None
        models = row["models"]
        manufacturers = row["manufacturers"]
        result.append(DeviceObservation(
            source="dns_sd",
            mac=base.mac,
            ip=ip,
            interface=row["interface"],
            role=base.role,
            hostname=row["hostname"],
            service_name=service_name,
            service_types=tuple(row["service_types"]),
            profile_hints=tuple(row["profile_hints"]),
            model=models[0] if models else None,
            manufacturer=manufacturers[0] if manufacturers else None,
        ))
    return result
