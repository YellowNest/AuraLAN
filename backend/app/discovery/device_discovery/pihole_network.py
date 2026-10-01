"""Read-only Pi-hole FTL identity enrichment for already-known clients.

Pi-hole can retain local client names after mDNS has gone quiet. AuraLAN reads
only known local FTL database locations, never modifies them, and only maps
rows back to MAC/IP addresses that were already observed on the LAN.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from pathlib import Path

from .base import DeviceObservation

CACHE_TTL_SECONDS = 60.0
MAX_CACHED_ROWS = 512
_env_path = os.environ.get("AURALAN_PIHOLE_FTL_DB")
CANDIDATE_DATABASES = tuple(
    ([Path(_env_path)] if _env_path else [])
    + [
        Path("/etc/pihole/pihole-FTL.db"),
        Path("/var/lib/pihole/pihole-FTL.db"),
    ]
)

_lock = threading.Lock()
_cached_at = 0.0
_cached_rows: list[dict[str, object]] = []
_cached_macs: set[str] = set()
_cached_ips: set[str] = set()


def _normalise_mac(value: str | None) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()


def _private_mac(value: str | None) -> bool:
    normalized = _normalise_mac(value)
    if len(normalized) < 2:
        return False
    try:
        return bool(int(normalized[:2], 16) & 0x02)
    except ValueError:
        return False


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_columns(connection: sqlite3.Connection, table: str) -> dict[str, str]:
    return {
        str(row[1]).lower(): str(row[1])
        for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")
    }


def _read_rows(path: Path, known_macs: set[str], known_ips: set[str]) -> list[dict[str, object]]:
    if not path.is_file() or not (known_macs or known_ips):
        return []
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.25)
    except (OSError, sqlite3.Error):
        return []
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "network" not in tables or "network_addresses" not in tables:
            return []

        network = _table_columns(connection, "network")
        addresses = _table_columns(connection, "network_addresses")
        if not {"id", "hwaddr"}.issubset(network) or not {"network_id", "ip"}.issubset(addresses):
            return []

        n_id = _quote_identifier(network["id"])
        n_mac = _quote_identifier(network["hwaddr"])
        a_network_id = _quote_identifier(addresses["network_id"])
        a_ip = _quote_identifier(addresses["ip"])
        name_expr = f'a.{_quote_identifier(addresses["name"])}' if "name" in addresses else "NULL"
        vendor_expr = f'n.{_quote_identifier(network["macvendor"])}' if "macvendor" in network else "NULL"
        last_seen = _quote_identifier(addresses["lastseen"]) if "lastseen" in addresses else None

        conditions: list[str] = []
        params: list[str | int] = []
        if known_macs:
            placeholders = ",".join("?" for _ in known_macs)
            normalized_mac = f"UPPER(REPLACE(REPLACE(n.{n_mac}, ':', ''), '-', ''))"
            conditions.append(f"{normalized_mac} IN ({placeholders})")
            params.extend(sorted(known_macs))
        if known_ips:
            placeholders = ",".join("?" for _ in known_ips)
            conditions.append(f"a.{a_ip} IN ({placeholders})")
            params.extend(sorted(known_ips))

        order_clause = f" ORDER BY a.{last_seen} DESC" if last_seen else ""
        query = (
            f"SELECT n.{n_mac} AS mac, a.{a_ip} AS ip, "
            f"{name_expr} AS name, {vendor_expr} AS vendor "
            f"FROM network n JOIN network_addresses a ON a.{a_network_id}=n.{n_id} "
            f"WHERE {' OR '.join(conditions)}"
            f"{order_clause} LIMIT ?"
        )
        params.append(MAX_CACHED_ROWS)
        return [dict(row) for row in connection.execute(query, params)]
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def _rows(known_macs: set[str], known_ips: set[str]) -> list[dict[str, object]]:
    global _cached_at, _cached_rows, _cached_macs, _cached_ips
    now = time.monotonic()
    with _lock:
        cache_fresh = now - _cached_at < CACHE_TTL_SECONDS
        targets_cached = known_macs.issubset(_cached_macs) and known_ips.issubset(_cached_ips)
        if cache_fresh and targets_cached:
            return list(_cached_rows)

    rows: list[dict[str, object]] = []
    for path in CANDIDATE_DATABASES:
        rows = _read_rows(path, known_macs, known_ips)
        if rows:
            break

    with _lock:
        _cached_rows = rows
        _cached_macs = set(known_macs)
        _cached_ips = set(known_ips)
        _cached_at = now
        return list(_cached_rows)


def _clean_name(value: object) -> str | None:
    name = str(value or "").strip().rstrip(".").removesuffix(".local")
    if not name or name == "*" or len(name) > 120:
        return None
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", name):
        return None
    return name


def observations(seed: list[DeviceObservation]) -> list[DeviceObservation]:
    by_mac: dict[str, DeviceObservation] = {}
    by_ip: dict[str, DeviceObservation] = {}
    for item in seed:
        normalized = _normalise_mac(item.mac)
        if normalized and normalized not in by_mac:
            by_mac[normalized] = item
        if item.ip and item.ip not in by_ip:
            by_ip[item.ip] = item

    known_macs = set(by_mac)
    known_ips = set(by_ip)
    if not known_macs and not known_ips:
        return []

    result: list[DeviceObservation] = []
    seen: set[tuple[str, str]] = set()
    for row in _rows(known_macs, known_ips):
        row_mac = _normalise_mac(str(row.get("mac") or ""))
        row_ip = str(row.get("ip") or "")
        base = by_mac.get(row_mac)

        # An IP match is only accepted if Pi-hole does not contradict the
        # currently observed MAC. This avoids identity carry-over after DHCP reuse.
        if base is None and row_ip:
            candidate = by_ip.get(row_ip)
            candidate_mac = _normalise_mac(candidate.mac) if candidate else ""
            if candidate and (not row_mac or row_mac == candidate_mac):
                base = candidate
        if base is None:
            continue

        key = (base.mac.upper(), base.ip or row_ip)
        if key in seen:
            continue

        hostname = _clean_name(row.get("name"))
        vendor = str(row.get("vendor") or "").strip() or None
        # Pi-hole's vendor is OUI-derived and therefore invalid for randomized
        # locally administered MAC addresses.
        if _private_mac(base.mac):
            vendor = None
        if not hostname and not vendor:
            continue

        seen.add(key)
        result.append(DeviceObservation(
            source="pihole_network",
            mac=base.mac,
            ip=base.ip or row_ip or None,
            interface=base.interface,
            role=base.role,
            hostname=hostname,
            manufacturer=vendor,
        ))
    return result
