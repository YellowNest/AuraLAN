"""Small, versioned SQLite store for user-owned device metadata and presence."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
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
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, int(time.time())),
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()

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
                    result[identifier] = item
                return result
            finally:
                connection.close()

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
