"""Small, versioned SQLite store for user-owned device metadata and presence."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 4
PRESENCE_WRITE_INTERVAL_SECONDS = 60


def default_data_dir() -> Path:
    """Return a writable per-installation state directory outside the source tree."""
    configured = os.environ.get("AURALAN_DATA_DIR")
    if configured:
        return Path(configured).expanduser()

    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / "auralan"

    return Path.home() / ".local" / "state" / "auralan"


class DeviceStore:
    """SQLite is intentionally limited to AuraLAN's own aliases and observations."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.path = self.data_dir / "auralan.db"
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
        connection = sqlite3.connect(self.path, timeout=1.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        """Bootstrap or repair the expected tables for the current database file.

        Each operation opens a fresh SQLite connection. Checking user_version
        notices when an administrator replaces or restores the database while
        AuraLAN is running, unlike a process-global readiness flag.
        """
        version_row = connection.execute("PRAGMA user_version").fetchone()
        version = int(version_row[0]) if version_row else 0
        required_tables = {
            "schema_migrations", "device_metadata", "device_presence", "device_identity_cache",
            "device_events", "device_inventory",
        }
        if version == SCHEMA_VERSION:
            existing_tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if required_tables.issubset(existing_tables):
                return
        if version > SCHEMA_VERSION:
            raise sqlite3.DatabaseError(
                f"AuraLAN database schema {version} is newer than supported schema {SCHEMA_VERSION}"
            )

        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)")
        connection.execute("""CREATE TABLE IF NOT EXISTS device_metadata (
            device_id TEXT PRIMARY KEY,
            alias TEXT,
            category_override TEXT,
            note TEXT,
            favorite INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS device_presence (
            device_id TEXT PRIMARY KEY,
            first_seen_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS device_identity_cache (
            device_id TEXT PRIMARY KEY,
            display_name TEXT,
            hostname TEXT,
            vendor TEXT,
            model TEXT,
            category TEXT,
            icon_key TEXT,
            source TEXT,
            confidence TEXT,
            updated_at INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS device_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            display_name TEXT,
            ip TEXT,
            mac TEXT,
            created_at INTEGER NOT NULL
        )""")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_events_created_at ON device_events(created_at DESC, id DESC)"
        )
        connection.execute("""CREATE TABLE IF NOT EXISTS device_inventory (
            device_id TEXT PRIMARY KEY,
            display_name TEXT,
            hostname TEXT,
            vendor TEXT,
            model TEXT,
            category TEXT,
            icon_key TEXT,
            ip TEXT,
            ip_addresses_json TEXT NOT NULL DEFAULT '[]',
            mac TEXT,
            mac_addresses_json TEXT NOT NULL DEFAULT '[]',
            mac_type TEXT,
            interface TEXT,
            connection_type TEXT,
            first_seen_at INTEGER,
            last_seen_at INTEGER,
            updated_at INTEGER NOT NULL
        )""")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_inventory_last_seen ON device_inventory(last_seen_at DESC, device_id)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, int(time.time())),
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()

    def readiness_check(self) -> dict[str, int | bool]:
        """Verify that AuraLAN can open and prepare its local state database.

        Health and staged upgrades use this deliberately small operation so a
        process is not considered ready merely because Uvicorn can answer HTTP.
        """
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                connection.execute("SELECT 1 FROM device_metadata LIMIT 1").fetchone()
                version_row = connection.execute("PRAGMA user_version").fetchone()
                return {
                    "ready": True,
                    "schema_version": int(version_row[0]) if version_row else 0,
                }
            finally:
                connection.close()

    def enrich(self, device_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return metadata/presence and write a bounded once-per-minute last-seen stamp."""
        if not device_ids:
            return {}
        unique = sorted(set(device_ids))
        now = int(time.time())
        placeholders = ",".join("?" for _ in unique)
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                existing = {
                    row["device_id"]: dict(row)
                    for row in connection.execute(
                        f"SELECT device_id, first_seen_at, last_seen_at FROM device_presence WHERE device_id IN ({placeholders})", unique
                    )
                }
                new_ids = set(unique) - set(existing)
                for identifier in unique:
                    previous = existing.get(identifier)
                    if previous is None:
                        connection.execute("INSERT INTO device_presence(device_id, first_seen_at, last_seen_at) VALUES (?, ?, ?)", (identifier, now, now))
                    elif now - int(previous["last_seen_at"]) >= PRESENCE_WRITE_INTERVAL_SECONDS:
                        connection.execute("UPDATE device_presence SET last_seen_at = ? WHERE device_id = ?", (now, identifier))
                metadata = {
                    row["device_id"]: dict(row)
                    for row in connection.execute(
                        f"SELECT device_id, alias, category_override, note, favorite, updated_at FROM device_metadata WHERE device_id IN ({placeholders})", unique
                    )
                }
                identity_cache = {
                    row["device_id"]: dict(row)
                    for row in connection.execute(
                        f"SELECT device_id, display_name, hostname, vendor, model, category, icon_key, source, confidence, updated_at "
                        f"FROM device_identity_cache WHERE device_id IN ({placeholders})", unique
                    )
                }
                connection.commit()
                refreshed = {
                    row["device_id"]: dict(row)
                    for row in connection.execute(
                        f"SELECT device_id, first_seen_at, last_seen_at FROM device_presence WHERE device_id IN ({placeholders})", unique
                    )
                }
                result: dict[str, dict[str, Any]] = {}
                for identifier in unique:
                    item = {**metadata.get(identifier, {}), **refreshed.get(identifier, {})}
                    if identifier in identity_cache:
                        cached = dict(identity_cache[identifier])
                        cached.pop("device_id", None)
                        item["cached_identity"] = cached
                    item["_new_presence"] = identifier in new_ids
                    result[identifier] = item
                return result
            finally:
                connection.close()

    def record_first_seen(self, records: list[dict[str, Any]], new_ids: set[str]) -> None:
        """Persist one local discovery event for genuinely new physical devices."""
        if not records or not new_ids:
            return

        now = int(time.time())
        events: list[tuple[str, str, str | None, str | None, str | None, int]] = []
        for record in records:
            observed_ids = {
                str(mac).upper().replace(":", "").lower()
                for mac in (record.get("mac_addresses") or [record.get("mac")])
                if mac
            }
            if not observed_ids or not observed_ids.issubset(new_ids):
                continue
            entity_id = str(record.get("id") or "").strip()
            if not entity_id:
                continue
            events.append((
                "device_first_seen",
                entity_id,
                str(record.get("display_name") or "").strip() or None,
                str(record.get("ip") or "").strip() or None,
                str(record.get("mac") or "").strip() or None,
                int(record.get("first_seen_at") or now),
            ))

        if not events:
            return

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                for event in events:
                    exists = connection.execute(
                        "SELECT 1 FROM device_events WHERE event_type = ? AND entity_id = ? LIMIT 1",
                        (event[0], event[1]),
                    ).fetchone()
                    if exists is None:
                        connection.execute(
                            "INSERT INTO device_events(event_type, entity_id, display_name, ip, mac, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            event,
                        )
                connection.commit()
            finally:
                connection.close()

    def recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent local inventory events without external enrichment."""
        bounded_limit = max(1, min(int(limit), 100))
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                return [
                    dict(row)
                    for row in connection.execute(
                        "SELECT id, event_type, entity_id, display_name, ip, mac, created_at "
                        "FROM device_events ORDER BY created_at DESC, id DESC LIMIT ?",
                        (bounded_limit,),
                    )
                ]
            finally:
                connection.close()

    @staticmethod
    def _normalise_mac(value: object) -> str:
        return str(value or "").strip().upper()

    def remember_inventory(self, records: list[dict[str, Any]]) -> None:
        """Persist the last trustworthy presentation of currently observed devices."""
        if not records:
            return

        now = int(time.time())
        rows: list[tuple[Any, ...]] = []
        for record in records:
            device_id = str(record.get("id") or "").strip()
            if not device_id:
                continue

            identity = record.get("identity") or {}
            display_identity = identity.get("display_name") or {}
            display_name = str(record.get("display_name") or "").strip() or None
            if display_identity.get("source") == "manual_alias":
                display_name = (
                    str(record.get("hostname") or "").strip()
                    or str(record.get("model") or "").strip()
                    or str(record.get("vendor") or "").strip()
                    or None
                )

            ip_addresses = [
                str(value).strip()
                for value in (record.get("ip_addresses") or [record.get("ip")])
                if value and str(value).strip() != "—"
            ]
            mac_addresses = [
                self._normalise_mac(value)
                for value in (record.get("mac_addresses") or [record.get("mac")])
                if value
            ]

            rows.append((
                device_id,
                display_name,
                str(record.get("hostname") or "").strip() or None,
                str(record.get("vendor") or "").strip() or None,
                str(record.get("model") or "").strip() or None,
                str(record.get("category") or "unknown"),
                str(record.get("icon_key") or "device_generic"),
                str(record.get("ip") or "").strip() or None,
                json.dumps(ip_addresses, separators=(",", ":")),
                self._normalise_mac(record.get("mac")) or None,
                json.dumps(mac_addresses, separators=(",", ":")),
                str(record.get("mac_type") or "unknown"),
                str(record.get("interface") or "").strip() or None,
                str(record.get("connection_type") or "unknown"),
                record.get("first_seen_at"),
                record.get("last_seen_at"),
                now,
            ))

        if not rows:
            return

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                connection.executemany(
                    """INSERT INTO device_inventory(
                        device_id, display_name, hostname, vendor, model, category, icon_key,
                        ip, ip_addresses_json, mac, mac_addresses_json, mac_type, interface,
                        connection_type, first_seen_at, last_seen_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        display_name=COALESCE(excluded.display_name, device_inventory.display_name),
                        hostname=COALESCE(excluded.hostname, device_inventory.hostname),
                        vendor=COALESCE(excluded.vendor, device_inventory.vendor),
                        model=COALESCE(excluded.model, device_inventory.model),
                        category=COALESCE(NULLIF(excluded.category, 'unknown'), device_inventory.category),
                        icon_key=COALESCE(NULLIF(excluded.icon_key, 'device_generic'), device_inventory.icon_key),
                        ip=COALESCE(excluded.ip, device_inventory.ip),
                        ip_addresses_json=CASE
                            WHEN excluded.ip_addresses_json != '[]' THEN excluded.ip_addresses_json
                            ELSE device_inventory.ip_addresses_json
                        END,
                        mac=COALESCE(excluded.mac, device_inventory.mac),
                        mac_addresses_json=CASE
                            WHEN excluded.mac_addresses_json != '[]' THEN excluded.mac_addresses_json
                            ELSE device_inventory.mac_addresses_json
                        END,
                        mac_type=COALESCE(NULLIF(excluded.mac_type, 'unknown'), device_inventory.mac_type),
                        interface=COALESCE(excluded.interface, device_inventory.interface),
                        connection_type=COALESCE(NULLIF(excluded.connection_type, 'unknown'), device_inventory.connection_type),
                        first_seen_at=COALESCE(
                            MIN(device_inventory.first_seen_at, excluded.first_seen_at),
                            device_inventory.first_seen_at,
                            excluded.first_seen_at
                        ),
                        last_seen_at=COALESCE(
                            MAX(device_inventory.last_seen_at, excluded.last_seen_at),
                            device_inventory.last_seen_at,
                            excluded.last_seen_at
                        ),
                        updated_at=excluded.updated_at""",
                    rows,
                )
                connection.commit()
            finally:
                connection.close()

    def known_devices(self, current_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return remembered devices that are not represented by the current discovery pass."""
        current_macs = {
            self._normalise_mac(mac)
            for record in current_records
            for mac in (record.get("mac_addresses") or [record.get("mac")])
            if mac
        }
        current_ids = {str(record.get("id") or "").strip() for record in current_records}
        current_ids.discard("")

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                rows = [dict(row) for row in connection.execute(
                    "SELECT * FROM device_inventory ORDER BY last_seen_at DESC, device_id"
                )]
                metadata = {
                    row["device_id"]: dict(row)
                    for row in connection.execute(
                        "SELECT device_id, alias, category_override, note, favorite "
                        "FROM device_metadata"
                    )
                }
            finally:
                connection.close()

        remembered: list[dict[str, Any]] = []
        for row in rows:
            try:
                mac_addresses = [
                    self._normalise_mac(value)
                    for value in json.loads(row.get("mac_addresses_json") or "[]")
                    if value
                ]
            except (TypeError, ValueError):
                mac_addresses = []
            if row["device_id"] in current_ids or current_macs.intersection(mac_addresses):
                continue

            try:
                ip_addresses = [
                    str(value)
                    for value in json.loads(row.get("ip_addresses_json") or "[]")
                    if value
                ]
            except (TypeError, ValueError):
                ip_addresses = []

            item_metadata = metadata.get(row["device_id"], {})
            category = item_metadata.get("category_override") or row.get("category") or "unknown"
            icon_key = row.get("icon_key") or "device_generic"
            display_name = row.get("display_name") or row.get("hostname") or row.get("model") or "Network device"
            sources = [{"source": "inventory_cache", "confidence": "medium"}]
            remembered.append({
                "id": row["device_id"],
                "display_name": display_name,
                "hostname": row.get("hostname"),
                "vendor": row.get("vendor"),
                "model": row.get("model"),
                "device_type": category,
                "category": category,
                "icon_key": icon_key,
                "ip": row.get("ip") or (ip_addresses[0] if ip_addresses else "—"),
                "ip_addresses": ip_addresses,
                "mac": row.get("mac") or (mac_addresses[0] if mac_addresses else "—"),
                "mac_addresses": mac_addresses,
                "mac_type": row.get("mac_type") or "unknown",
                "interface": row.get("interface"),
                "connection_type": row.get("connection_type") or "unknown",
                "online": None,
                "state": "known",
                "signal_dbm": None,
                "signal_quality": None,
                "dhcp": False,
                "lease_expires_at": None,
                "lease": {"present": False, "expires_at": None},
                "first_seen_at": row.get("first_seen_at"),
                "last_seen_at": row.get("last_seen_at"),
                "identity": {
                    "display_name": {"value": display_name, "source": "inventory_cache", "confidence": "medium"},
                    "vendor": (
                        {"value": row["vendor"], "source": "inventory_cache", "confidence": "medium"}
                        if row.get("vendor") else None
                    ),
                    "model": (
                        {"value": row["model"], "source": "inventory_cache", "confidence": "medium"}
                        if row.get("model") else None
                    ),
                    "device_type": {"value": category, "source": "inventory_cache", "confidence": "medium"},
                    "sources": sources,
                },
                "metadata": {
                    "alias": item_metadata.get("alias"),
                    "category_override": item_metadata.get("category_override"),
                    "note": item_metadata.get("note"),
                    "favorite": bool(item_metadata.get("favorite")),
                },
                "observations": [],
            })

        return remembered

    def remember_identities(self, records: list[dict[str, Any]]) -> None:
        """Keep the last trustworthy identity for the same observed MAC."""
        now = int(time.time())
        candidates: list[tuple[Any, ...]] = []
        for record in records:
            identifier = str(record.get("id") or "").strip()
            if not identifier:
                continue
            identity = record.get("identity") or {}
            display = identity.get("display_name") or {}
            display_source = str(display.get("source") or "")
            display_confidence = str(display.get("confidence") or "")
            display_name = (
                str(display.get("value") or "").strip()
                if display_source not in {"heuristic", "manual_alias", "identity_cache"} and display_confidence in {"high", "medium"}
                else None
            )
            hostname = str(record.get("hostname") or "").strip() or None
            vendor = str(record.get("vendor") or "").strip() or None
            model = str(record.get("model") or "").strip() or None
            category = str(record.get("category") or "").strip()
            category = category if category and category != "unknown" else None
            icon_key = str(record.get("icon_key") or "").strip()
            icon_key = icon_key if icon_key and icon_key != "device_generic" else None
            if not any((display_name, hostname, vendor, model, category, icon_key)):
                continue
            candidates.append((
                identifier, display_name, hostname, vendor, model, category, icon_key,
                display_source or None, display_confidence or None, now,
            ))

        if not candidates:
            return

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                connection.executemany(
                    """INSERT INTO device_identity_cache(
                        device_id, display_name, hostname, vendor, model, category, icon_key, source, confidence, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        display_name=COALESCE(excluded.display_name, device_identity_cache.display_name),
                        hostname=COALESCE(excluded.hostname, device_identity_cache.hostname),
                        vendor=COALESCE(excluded.vendor, device_identity_cache.vendor),
                        model=COALESCE(excluded.model, device_identity_cache.model),
                        category=COALESCE(excluded.category, device_identity_cache.category),
                        icon_key=COALESCE(excluded.icon_key, device_identity_cache.icon_key),
                        source=COALESCE(excluded.source, device_identity_cache.source),
                        confidence=COALESCE(excluded.confidence, device_identity_cache.confidence),
                        updated_at=excluded.updated_at""",
                    candidates,
                )
                connection.commit()
            finally:
                connection.close()

    def update_metadata(
        self,
        device_id: str,
        *,
        alias: str | None | object = ...,
        category_override: str | None | object = ...,
        note: str | None | object = ...,
        favorite: bool | object = ...,
    ) -> dict[str, Any]:
        """Persist AuraLAN-local inventory metadata; no system configuration is touched."""
        now = int(time.time())
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                current = connection.execute(
                    "SELECT alias, category_override, note, favorite FROM device_metadata WHERE device_id = ?",
                    (device_id,),
                ).fetchone()
                next_alias = current["alias"] if current and alias is ... else (alias if alias is not ... else None)
                next_category = current["category_override"] if current and category_override is ... else (category_override if category_override is not ... else None)
                next_note = current["note"] if current and note is ... else (note if note is not ... else None)
                next_favorite = bool(current["favorite"]) if current and favorite is ... else (bool(favorite) if favorite is not ... else False)
                connection.execute(
                    "INSERT INTO device_metadata(device_id, alias, category_override, note, favorite, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(device_id) DO UPDATE SET alias=excluded.alias, category_override=excluded.category_override, "
                    "note=excluded.note, favorite=excluded.favorite, updated_at=excluded.updated_at",
                    (device_id, next_alias, next_category, next_note, int(next_favorite), now),
                )
                if next_alias:
                    connection.execute(
                        "UPDATE device_events SET display_name = ? "
                        "WHERE event_type = 'device_first_seen' AND entity_id = ?",
                        (next_alias, device_id),
                    )
                connection.commit()
                return {
                    "alias": next_alias,
                    "category_override": next_category,
                    "note": next_note,
                    "favorite": next_favorite,
                    "updated_at": now,
                }
            finally:
                connection.close()


_store: DeviceStore | None = None


def store() -> DeviceStore:
    global _store
    if _store is None:
        _store = DeviceStore()
    return _store
