"""Small, versioned SQLite store for user-owned device metadata and presence."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 10
NOTIFICATION_EVENT_TYPES = ("device_first_seen", "favorite_not_seen", "favorite_seen_again")
PRESENCE_WRITE_INTERVAL_SECONDS = 60
DEFAULT_WATCH_MISSING_GRACE_SECONDS = 120
DEFAULT_PRESENCE_MISSING_GRACE_SECONDS = 180
MAX_WATCH_MISSING_GRACE_SECONDS = 86400
PRESENCE_HISTORY_PER_DEVICE_LIMIT = 200
PRESENCE_HISTORY_TOTAL_LIMIT = 5000
SERVICE_SCAN_PER_DEVICE_LIMIT = 20
SERVICE_SCAN_TOTAL_LIMIT = 2000

WATCH_SEEN = 0
WATCH_NOT_SEEN = 1
WATCH_PENDING_NOT_SEEN = 2

PRESENCE_SEEN = 0
PRESENCE_NOT_SEEN = 1
PRESENCE_PENDING_NOT_SEEN = 2


def presence_missing_grace_seconds() -> int:
    """Return the configured absence grace period for device presence history."""
    raw = os.environ.get(
        "AURALAN_PRESENCE_MISSING_GRACE",
        str(DEFAULT_PRESENCE_MISSING_GRACE_SECONDS),
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PRESENCE_MISSING_GRACE_SECONDS
    return max(0, min(value, MAX_WATCH_MISSING_GRACE_SECONDS))


def watch_missing_grace_seconds() -> int:
    """Return the configured favorite-watch absence grace period."""
    raw = os.environ.get(
        "AURALAN_WATCH_MISSING_GRACE",
        str(DEFAULT_WATCH_MISSING_GRACE_SECONDS),
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WATCH_MISSING_GRACE_SECONDS
    return max(0, min(value, MAX_WATCH_MISSING_GRACE_SECONDS))



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
            "device_events", "device_inventory", "device_watch_state", "notification_cursors",
            "device_presence_state", "device_presence_history", "network_baseline", "device_service_scans",
        }
        required_indexes = {
            "idx_device_events_created_at",
            "idx_device_events_type_entity",
            "idx_device_inventory_last_seen",
            "idx_device_presence_history_device_time",
            "idx_device_service_scans_device_time",
        }
        if version == SCHEMA_VERSION:
            schema_objects = {
                (str(row[0]), str(row[1]))
                for row in connection.execute(
                    "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'index')"
                )
            }
            existing_tables = {name for kind, name in schema_objects if kind == "table"}
            existing_indexes = {name for kind, name in schema_objects if kind == "index"}
            if required_tables.issubset(existing_tables) and required_indexes.issubset(existing_indexes):
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
            location TEXT,
            tags_json TEXT NOT NULL DEFAULT '[]',
            updated_at INTEGER NOT NULL
        )""")
        metadata_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(device_metadata)")
        }
        if "location" not in metadata_columns:
            connection.execute("ALTER TABLE device_metadata ADD COLUMN location TEXT")
        if "tags_json" not in metadata_columns:
            connection.execute("ALTER TABLE device_metadata ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'")
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
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL
        )""")
        event_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(device_events)")
        }
        if "details_json" not in event_columns:
            connection.execute(
                "ALTER TABLE device_events ADD COLUMN details_json TEXT NOT NULL DEFAULT '{}'"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_events_created_at ON device_events(created_at DESC, id DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_events_type_entity ON device_events(event_type, entity_id)"
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
        connection.execute("""CREATE TABLE IF NOT EXISTS device_watch_state (
            device_id TEXT PRIMARY KEY,
            not_seen INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS notification_cursors (
            channel TEXT PRIMARY KEY,
            last_event_id INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS device_presence_state (
            device_id TEXT PRIMARY KEY,
            state INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS device_presence_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            display_name TEXT,
            created_at INTEGER NOT NULL
        )""")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_presence_history_device_time "
            "ON device_presence_history(device_id, created_at DESC, id DESC)"
        )
        connection.execute("""CREATE TABLE IF NOT EXISTS network_baseline (
            entity_id TEXT PRIMARY KEY,
            identity_ids_json TEXT NOT NULL DEFAULT '[]',
            display_name TEXT,
            captured_at INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS device_service_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            ip TEXT NOT NULL,
            open_ports_json TEXT NOT NULL DEFAULT '[]',
            checked_at INTEGER NOT NULL
        )""")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_service_scans_device_time "
            "ON device_service_scans(device_id, checked_at DESC, id DESC)"
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
                        f"SELECT device_id, alias, category_override, note, favorite, location, tags_json, updated_at FROM device_metadata WHERE device_id IN ({placeholders})", unique
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
                    try:
                        item["tags"] = [
                            str(value)
                            for value in json.loads(item.pop("tags_json", "[]") or "[]")
                            if str(value).strip()
                        ]
                    except (TypeError, ValueError):
                        item.pop("tags_json", None)
                        item["tags"] = []
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

    @staticmethod
    def _decode_event_details(value: object) -> dict[str, Any]:
        try:
            loaded = json.loads(str(value or "{}"))
        except (TypeError, ValueError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent local activity without external enrichment."""
        bounded_limit = max(1, min(int(limit), 100))
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                rows = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT id, event_type, entity_id, display_name, ip, mac, details_json, created_at "
                        "FROM device_events ORDER BY created_at DESC, id DESC LIMIT ?",
                        (bounded_limit,),
                    )
                ]
            finally:
                connection.close()

        for row in rows:
            row["details"] = self._decode_event_details(row.pop("details_json", "{}"))
        return rows

    def activity_summary_since(self, since: int) -> dict[str, int]:
        """Return aggregate Activity Center counts since a Unix timestamp."""
        threshold = max(0, int(since))
        groups = {
            "total": 0,
            "new_devices": 0,
            "watch_changes": 0,
            "service_changes": 0,
            "baseline_changes": 0,
        }
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                rows = connection.execute(
                    "SELECT event_type, COUNT(*) AS count "
                    "FROM device_events WHERE created_at >= ? "
                    "GROUP BY event_type",
                    (threshold,),
                ).fetchall()
            finally:
                connection.close()

        for row in rows:
            event_type = str(row["event_type"])
            count = int(row["count"])
            groups["total"] += count
            if event_type == "device_first_seen":
                groups["new_devices"] += count
            elif event_type in {"favorite_not_seen", "favorite_seen_again"}:
                groups["watch_changes"] += count
            elif event_type == "service_exposure_changed":
                groups["service_changes"] += count
            elif event_type in {"baseline_captured", "baseline_cleared"}:
                groups["baseline_changes"] += count
        return groups

    def activity_daily_counts(self, days: int = 7, *, now: int | None = None) -> list[dict[str, int]]:
        """Return rolling 24-hour Activity Center buckets, oldest first."""
        bounded_days = max(1, min(int(days), 31))
        end_at = int(time.time()) if now is None else int(now)
        day_seconds = 24 * 60 * 60
        start_at = end_at - (bounded_days * day_seconds)

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                rows = connection.execute(
                    "SELECT event_type, created_at FROM device_events "
                    "WHERE created_at >= ? AND created_at <= ? "
                    "ORDER BY created_at ASC, id ASC",
                    (start_at, end_at),
                ).fetchall()
            finally:
                connection.close()

        buckets = []
        for index in range(bounded_days):
            bucket_start = start_at + (index * day_seconds)
            buckets.append({
                "start_at": bucket_start,
                "total": 0,
                "new_devices": 0,
                "watch_changes": 0,
                "service_changes": 0,
                "baseline_changes": 0,
            })

        for row in rows:
            created_at = int(row["created_at"])
            index = min(
                bounded_days - 1,
                max(0, (created_at - start_at) // day_seconds),
            )
            bucket = buckets[index]
            bucket["total"] += 1
            event_type = str(row["event_type"])
            if event_type == "device_first_seen":
                bucket["new_devices"] += 1
            elif event_type in {"favorite_not_seen", "favorite_seen_again"}:
                bucket["watch_changes"] += 1
            elif event_type == "service_exposure_changed":
                bucket["service_changes"] += 1
            elif event_type in {"baseline_captured", "baseline_cleared"}:
                bucket["baseline_changes"] += 1

        return buckets

    def record_watch_transitions(self, records: list[dict[str, Any]]) -> None:
        """Record stable watch-state changes for user-favorited devices.

        A single missed discovery pass is weak evidence. AuraLAN therefore starts
        a persisted pending state and only emits favorite_not_seen after the
        configured grace period. A positive observation clears the pending state
        immediately and confirms a return immediately after a real absence.
        """
        favorites = [
            record for record in records
            if bool((record.get("metadata") or {}).get("favorite"))
            and str(record.get("id") or "").strip()
        ]
        if not favorites:
            return

        now = int(time.time())
        grace_seconds = watch_missing_grace_seconds()

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                for record in favorites:
                    device_id = str(record.get("id") or "").strip()
                    currently_missing = record.get("state") == "known"
                    previous = connection.execute(
                        "SELECT not_seen, updated_at FROM device_watch_state WHERE device_id = ?",
                        (device_id,),
                    ).fetchone()

                    if previous is None:
                        initial_state = WATCH_PENDING_NOT_SEEN if currently_missing else WATCH_SEEN
                        connection.execute(
                            "INSERT INTO device_watch_state(device_id, not_seen, updated_at) VALUES (?, ?, ?)",
                            (device_id, initial_state, now),
                        )
                        continue

                    watch_state = int(previous["not_seen"])
                    state_since = int(previous["updated_at"])

                    if currently_missing:
                        if watch_state == WATCH_NOT_SEEN:
                            continue

                        if watch_state == WATCH_SEEN:
                            if grace_seconds == 0:
                                next_state = WATCH_NOT_SEEN
                            else:
                                connection.execute(
                                    "UPDATE device_watch_state SET not_seen = ?, updated_at = ? WHERE device_id = ?",
                                    (WATCH_PENDING_NOT_SEEN, now, device_id),
                                )
                                continue
                        else:
                            if now - state_since < grace_seconds:
                                continue
                            next_state = WATCH_NOT_SEEN

                        event_type = "favorite_not_seen"
                    else:
                        if watch_state == WATCH_SEEN:
                            continue
                        if watch_state == WATCH_PENDING_NOT_SEEN:
                            connection.execute(
                                "UPDATE device_watch_state SET not_seen = ?, updated_at = ? WHERE device_id = ?",
                                (WATCH_SEEN, now, device_id),
                            )
                            continue

                        next_state = WATCH_SEEN
                        event_type = "favorite_seen_again"

                    display_name = str(record.get("display_name") or "").strip() or None
                    ip = str(record.get("ip") or "").strip() or None
                    mac = str(record.get("mac") or "").strip() or None
                    connection.execute(
                        "INSERT INTO device_events(event_type, entity_id, display_name, ip, mac, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (event_type, device_id, display_name, ip, mac, now),
                    )
                    connection.execute(
                        "UPDATE device_watch_state SET not_seen = ?, updated_at = ? WHERE device_id = ?",
                        (next_state, now, device_id),
                    )

                connection.commit()
            finally:
                connection.close()

    def record_presence_transitions(self, records: list[dict[str, Any]]) -> None:
        """Persist debounced seen/not-seen transitions for all inventoried devices."""
        candidates = [
            record
            for record in records
            if str(record.get("id") or "").strip()
        ]
        if not candidates:
            return

        now = int(time.time())
        grace_seconds = presence_missing_grace_seconds()

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                for record in candidates:
                    device_id = str(record.get("id") or "").strip()
                    currently_missing = record.get("state") == "known"
                    previous = connection.execute(
                        "SELECT state, updated_at FROM device_presence_state WHERE device_id = ?",
                        (device_id,),
                    ).fetchone()

                    if previous is None:
                        initial_state = PRESENCE_NOT_SEEN if currently_missing else PRESENCE_SEEN
                        connection.execute(
                            "INSERT INTO device_presence_state(device_id, state, updated_at) VALUES (?, ?, ?)",
                            (device_id, initial_state, now),
                        )
                        continue

                    presence_state = int(previous["state"])
                    state_since = int(previous["updated_at"])

                    if currently_missing:
                        if presence_state == PRESENCE_NOT_SEEN:
                            continue

                        if presence_state == PRESENCE_SEEN:
                            if grace_seconds == 0:
                                next_state = PRESENCE_NOT_SEEN
                            else:
                                connection.execute(
                                    "UPDATE device_presence_state SET state = ?, updated_at = ? WHERE device_id = ?",
                                    (PRESENCE_PENDING_NOT_SEEN, now, device_id),
                                )
                                continue
                        else:
                            if now - state_since < grace_seconds:
                                continue
                            next_state = PRESENCE_NOT_SEEN

                        event_type = "device_not_seen"
                    else:
                        if presence_state == PRESENCE_SEEN:
                            continue
                        if presence_state == PRESENCE_PENDING_NOT_SEEN:
                            connection.execute(
                                "UPDATE device_presence_state SET state = ?, updated_at = ? WHERE device_id = ?",
                                (PRESENCE_SEEN, now, device_id),
                            )
                            continue

                        next_state = PRESENCE_SEEN
                        event_type = "device_seen_again"

                    display_name = str(record.get("display_name") or "").strip() or None
                    connection.execute(
                        "INSERT INTO device_presence_history(device_id, event_type, display_name, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (device_id, event_type, display_name, now),
                    )
                    connection.execute(
                        "UPDATE device_presence_state SET state = ?, updated_at = ? WHERE device_id = ?",
                        (next_state, now, device_id),
                    )

                    connection.execute(
                        "DELETE FROM device_presence_history WHERE device_id = ? AND id NOT IN ("
                        "SELECT id FROM device_presence_history WHERE device_id = ? "
                        "ORDER BY created_at DESC, id DESC LIMIT ?"
                        ")",
                        (device_id, device_id, PRESENCE_HISTORY_PER_DEVICE_LIMIT),
                    )

                connection.execute(
                    "DELETE FROM device_presence_history WHERE id NOT IN ("
                    "SELECT id FROM device_presence_history ORDER BY created_at DESC, id DESC LIMIT ?"
                    ")",
                    (PRESENCE_HISTORY_TOTAL_LIMIT,),
                )
                connection.commit()
            finally:
                connection.close()

    def presence_history(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return the local debounced presence timeline for one known device."""
        bounded_limit = max(1, min(int(limit), 200))
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                return [
                    dict(row)
                    for row in connection.execute(
                        "SELECT id, device_id, event_type, display_name, created_at "
                        "FROM device_presence_history WHERE device_id = ? "
                        "ORDER BY created_at DESC, id DESC LIMIT ?",
                        (str(device_id), bounded_limit),
                    )
                ]
            finally:
                connection.close()

    @staticmethod
    def _decode_port_list(value: object) -> list[int]:
        try:
            loaded = json.loads(str(value or "[]"))
        except (TypeError, ValueError):
            return []
        if not isinstance(loaded, list):
            return []
        ports = []
        for item in loaded:
            try:
                port = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535:
                ports.append(port)
        return sorted(set(ports))

    def record_service_scan(
        self,
        device_id: str,
        ip: str,
        open_ports: list[int],
        *,
        checked_at: int | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        """Persist one bounded on-demand service snapshot and compare the previous one."""
        identifier = str(device_id or "").strip()
        target = str(ip or "").strip()
        if not identifier or not target:
            raise ValueError("Device ID and target IP are required")

        ports = sorted({
            int(port)
            for port in open_ports
            if 1 <= int(port) <= 65535
        })
        timestamp = int(time.time()) if checked_at is None else int(checked_at)

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                previous = connection.execute(
                    "SELECT open_ports_json, checked_at FROM device_service_scans "
                    "WHERE device_id = ? ORDER BY checked_at DESC, id DESC LIMIT 1",
                    (identifier,),
                ).fetchone()

                previous_ports = self._decode_port_list(previous["open_ports_json"]) if previous else []
                current_ports = set(ports)
                before_ports = set(previous_ports)
                newly_open = sorted(current_ports - before_ports) if previous else []
                no_longer_open = sorted(before_ports - current_ports) if previous else []
                changed = bool(previous and (newly_open or no_longer_open))

                connection.execute(
                    "INSERT INTO device_service_scans(device_id, ip, open_ports_json, checked_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        identifier,
                        target,
                        json.dumps(ports, separators=(",", ":")),
                        timestamp,
                    ),
                )
                if changed:
                    details = {
                        "newly_open": newly_open,
                        "no_longer_open": no_longer_open,
                        "open_ports": ports,
                        "previous_checked_at": int(previous["checked_at"]),
                    }
                    connection.execute(
                        "INSERT INTO device_events("
                        "event_type, entity_id, display_name, ip, mac, details_json, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            "service_exposure_changed",
                            identifier,
                            str(display_name or "").strip() or None,
                            target,
                            None,
                            json.dumps(details, separators=(",", ":")),
                            timestamp,
                        ),
                    )
                connection.execute(
                    "DELETE FROM device_service_scans WHERE id IN ("
                    "SELECT id FROM device_service_scans WHERE device_id = ? "
                    "ORDER BY checked_at DESC, id DESC LIMIT -1 OFFSET ?"
                    ")",
                    (identifier, SERVICE_SCAN_PER_DEVICE_LIMIT),
                )
                connection.execute(
                    "DELETE FROM device_service_scans WHERE id NOT IN ("
                    "SELECT id FROM device_service_scans "
                    "ORDER BY checked_at DESC, id DESC LIMIT ?"
                    ")",
                    (SERVICE_SCAN_TOTAL_LIMIT,),
                )
                connection.commit()
            finally:
                connection.close()

        return {
            "device_id": identifier,
            "ip": target,
            "checked_at": timestamp,
            "open_ports": ports,
            "previous_checked_at": int(previous["checked_at"]) if previous else None,
            "previous_open_ports": previous_ports,
            "newly_open": newly_open,
            "no_longer_open": no_longer_open,
            "changed": changed,
        }

    def service_scan_history(self, device_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent on-demand service snapshots for one AuraLAN device."""
        bounded_limit = max(1, min(int(limit), SERVICE_SCAN_PER_DEVICE_LIMIT))
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                rows = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT id, device_id, ip, open_ports_json, checked_at "
                        "FROM device_service_scans WHERE device_id = ? "
                        "ORDER BY checked_at DESC, id DESC LIMIT ?",
                        (str(device_id), bounded_limit),
                    )
                ]
            finally:
                connection.close()

        for row in rows:
            row["open_ports"] = self._decode_port_list(row.pop("open_ports_json", "[]"))
        return rows

    def latest_event_id(self) -> int:
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                row = connection.execute("SELECT COALESCE(MAX(id), 0) FROM device_events").fetchone()
                return int(row[0]) if row else 0
            finally:
                connection.close()

    def pending_event_count(self, event_id: int) -> int:
        """Count actual persisted events after a notification cursor."""
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                event_types = tuple(NOTIFICATION_EVENT_TYPES)
                marks = ",".join("?" for _ in event_types)
                row = connection.execute(
                    f"SELECT COUNT(*) FROM device_events WHERE id > ? AND event_type IN ({marks})",
                    (int(event_id), *event_types),
                ).fetchone()
                return int(row[0]) if row else 0
            finally:
                connection.close()

    def events_after(self, event_id: int, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 100))
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                event_types = tuple(NOTIFICATION_EVENT_TYPES)
                marks = ",".join("?" for _ in event_types)
                rows = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT id, event_type, entity_id, display_name, ip, mac, details_json, created_at "
                        f"FROM device_events WHERE id > ? AND event_type IN ({marks}) "
                        "ORDER BY id ASC LIMIT ?",
                        (int(event_id), *event_types, bounded_limit),
                    )
                ]
                for row in rows:
                    row["details"] = self._decode_event_details(row.pop("details_json", "{}"))
                return rows
            finally:
                connection.close()

    def notification_cursor(self, channel: str) -> int | None:
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                row = connection.execute(
                    "SELECT last_event_id FROM notification_cursors WHERE channel = ?",
                    (channel,),
                ).fetchone()
                return int(row["last_event_id"]) if row else None
            finally:
                connection.close()

    def set_notification_cursor(self, channel: str, event_id: int) -> None:
        now = int(time.time())
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                connection.execute(
                    "INSERT INTO notification_cursors(channel, last_event_id, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(channel) DO UPDATE SET last_event_id=excluded.last_event_id, updated_at=excluded.updated_at",
                    (channel, int(event_id), now),
                )
                connection.commit()
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

                # Older AuraLAN installations can already contain a large
                # remembered inventory but no first-seen event rows. One set-based
                # statement backfills every missing event; the indexed NOT EXISTS
                # check avoids the previous per-device query loop on every snapshot.
                connection.execute(
                    """INSERT INTO device_events(event_type, entity_id, display_name, ip, mac, created_at)
                       SELECT 'device_first_seen',
                              inventory.device_id,
                              COALESCE(metadata.alias, inventory.display_name, inventory.hostname, inventory.model),
                              inventory.ip,
                              inventory.mac,
                              COALESCE(inventory.first_seen_at, inventory.updated_at)
                       FROM device_inventory AS inventory
                       LEFT JOIN device_metadata AS metadata ON metadata.device_id = inventory.device_id
                       WHERE NOT EXISTS (
                           SELECT 1 FROM device_events AS event
                           WHERE event.event_type = 'device_first_seen'
                             AND event.entity_id = inventory.device_id
                       )"""
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
                        "SELECT device_id, alias, category_override, note, favorite, location, tags_json "
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
            try:
                item_tags = [
                    str(value)
                    for value in json.loads(item_metadata.get("tags_json") or "[]")
                    if str(value).strip()
                ]
            except (TypeError, ValueError):
                item_tags = []
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
                    "location": item_metadata.get("location"),
                    "tags": item_tags,
                },
                "observations": [],
            })

        return remembered

    def capture_baseline(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Replace the local network baseline with devices observed right now."""
        observed = [
            record for record in records
            if record.get("state") != "known" and str(record.get("id") or "").strip()
        ]
        if not observed:
            raise ValueError("No currently observed devices are available for a baseline")

        captured_at = int(time.time())
        rows: list[tuple[str, str, str | None, int]] = []
        for record in observed:
            entity_id = str(record.get("id") or "").strip()
            identities = sorted(self._record_identity_ids(record))
            if not identities:
                identities = [entity_id]
            rows.append((
                entity_id,
                json.dumps(identities, separators=(",", ":")),
                str(record.get("display_name") or "").strip() or None,
                captured_at,
            ))

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM network_baseline")
                connection.executemany(
                    "INSERT INTO network_baseline(entity_id, identity_ids_json, display_name, captured_at) "
                    "VALUES (?, ?, ?, ?)",
                    rows,
                )
                connection.execute(
                    "INSERT INTO device_events("
                    "event_type, entity_id, display_name, ip, mac, details_json, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "baseline_captured",
                        "network",
                        None,
                        None,
                        None,
                        json.dumps({"device_count": len(rows)}, separators=(",", ":")),
                        captured_at,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

        return self.baseline_status(records)

    def clear_baseline(self) -> None:
        """Remove the operator-defined network baseline without touching inventory."""
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                previous = connection.execute(
                    "SELECT COUNT(*) AS count, MAX(captured_at) AS captured_at FROM network_baseline"
                ).fetchone()
                device_count = int(previous["count"]) if previous else 0
                connection.execute("DELETE FROM network_baseline")
                if device_count:
                    connection.execute(
                        "INSERT INTO device_events("
                        "event_type, entity_id, display_name, ip, mac, details_json, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            "baseline_cleared",
                            "network",
                            None,
                            None,
                            None,
                            json.dumps({"device_count": device_count}, separators=(",", ":")),
                            int(time.time()),
                        ),
                    )
                connection.commit()
            finally:
                connection.close()

    def baseline_status(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Compare current observations with the last operator-captured baseline."""
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                rows = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT entity_id, identity_ids_json, display_name, captured_at "
                        "FROM network_baseline ORDER BY entity_id"
                    )
                ]
            finally:
                connection.close()

        if not rows:
            return {
                "configured": False,
                "captured_at": None,
                "device_count": 0,
                "current_count": sum(1 for record in records if record.get("state") != "known"),
                "new_count": 0,
                "missing_count": 0,
                "new_device_ids": [],
                "missing_device_ids": [],
            }

        baseline_members: list[tuple[dict[str, Any], set[str]]] = []
        baseline_identity_union: set[str] = set()
        for row in rows:
            try:
                identities = {
                    str(value).strip()
                    for value in json.loads(row.get("identity_ids_json") or "[]")
                    if str(value).strip()
                }
            except (TypeError, ValueError):
                identities = set()
            entity_id = str(row.get("entity_id") or "").strip()
            if entity_id:
                identities.add(entity_id)
            baseline_members.append((row, identities))
            baseline_identity_union.update(identities)

        current = [record for record in records if record.get("state") != "known"]
        current_identity_union: set[str] = set()
        record_identities: dict[str, set[str]] = {}
        for record in records:
            entity_id = str(record.get("id") or "").strip()
            if not entity_id:
                continue
            identities = self._record_identity_ids(record)
            record_identities[entity_id] = identities
            if record.get("state") != "known":
                current_identity_union.update(identities)

        new_device_ids = [
            str(record.get("id"))
            for record in current
            if self._record_identity_ids(record).isdisjoint(baseline_identity_union)
        ]

        missing_device_ids: list[str] = []
        for row, identities in baseline_members:
            if not identities.isdisjoint(current_identity_union):
                continue
            remembered_id = next(
                (
                    record_id
                    for record_id, known_identities in record_identities.items()
                    if not identities.isdisjoint(known_identities)
                ),
                None,
            )
            missing_device_ids.append(remembered_id or str(row.get("entity_id") or ""))

        return {
            "configured": True,
            "captured_at": max(int(row.get("captured_at") or 0) for row, _ in baseline_members) or None,
            "device_count": len(baseline_members),
            "current_count": len(current),
            "new_count": len(new_device_ids),
            "missing_count": len(missing_device_ids),
            "new_device_ids": sorted(set(new_device_ids)),
            "missing_device_ids": sorted({value for value in missing_device_ids if value}),
        }

    @classmethod
    def _record_identity_ids(cls, record: dict[str, Any]) -> set[str]:
        """Return stable local identity keys for a possibly multi-interface device."""
        identities: set[str] = set()
        entity_id = str(record.get("id") or "").strip()
        if entity_id:
            identities.add(entity_id)
        for value in record.get("mac_addresses") or [record.get("mac")]:
            identity = cls._identity_id_from_mac(value)
            if identity:
                identities.add(identity)
        return identities

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

    @staticmethod
    def _identity_id_from_mac(value: object) -> str:
        return str(value or "").strip().replace(":", "").replace("-", "").lower()

    def forget_device(self, device_id: str) -> bool:
        """Remove AuraLAN-owned memory for one remembered physical device."""
        requested_id = str(device_id or "").strip()
        if not requested_id:
            return False

        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)

                linked_ids = {requested_id}
                inventory_row = connection.execute(
                    "SELECT mac, mac_addresses_json FROM device_inventory WHERE device_id = ?",
                    (requested_id,),
                ).fetchone()

                if inventory_row is not None:
                    raw_macs: list[object] = [inventory_row["mac"]]
                    try:
                        raw_macs.extend(json.loads(inventory_row["mac_addresses_json"] or "[]"))
                    except (TypeError, ValueError):
                        pass
                    linked_ids.update(
                        identifier
                        for identifier in (
                            self._identity_id_from_mac(value)
                            for value in raw_macs
                        )
                        if identifier
                    )

                placeholders = ",".join("?" for _ in linked_ids)
                values = tuple(sorted(linked_ids))
                deleted = 0

                for table in (
                    "device_metadata",
                    "device_presence",
                    "device_identity_cache",
                    "device_inventory",
                    "device_watch_state",
                    "device_presence_state",
                    "device_service_scans",
                ):
                    cursor = connection.execute(
                        f"DELETE FROM {table} WHERE device_id IN ({placeholders})",
                        values,
                    )
                    deleted += max(0, int(cursor.rowcount))

                cursor = connection.execute(
                    f"DELETE FROM device_presence_history WHERE device_id IN ({placeholders})",
                    values,
                )
                deleted += max(0, int(cursor.rowcount))

                cursor = connection.execute(
                    f"DELETE FROM device_events WHERE entity_id IN ({placeholders})",
                    values,
                )
                deleted += max(0, int(cursor.rowcount))

                baseline_rows = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT entity_id, identity_ids_json FROM network_baseline"
                    )
                ]
                for baseline_row in baseline_rows:
                    try:
                        baseline_ids = {
                            str(value).strip()
                            for value in json.loads(baseline_row.get("identity_ids_json") or "[]")
                            if str(value).strip()
                        }
                    except (TypeError, ValueError):
                        baseline_ids = set()
                    baseline_ids.add(str(baseline_row.get("entity_id") or "").strip())
                    if baseline_ids.intersection(linked_ids):
                        connection.execute(
                            "DELETE FROM network_baseline WHERE entity_id = ?",
                            (baseline_row["entity_id"],),
                        )

                connection.commit()
                return deleted > 0
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
        location: str | None | object = ...,
        tags: list[str] | object = ...,
    ) -> dict[str, Any]:
        """Persist AuraLAN-local inventory metadata; no system configuration is touched."""
        now = int(time.time())
        with self._lock:
            connection = self._connect()
            try:
                self._ensure_schema(connection)
                current = connection.execute(
                    "SELECT alias, category_override, note, favorite, location, tags_json FROM device_metadata WHERE device_id = ?",
                    (device_id,),
                ).fetchone()
                next_alias = current["alias"] if current and alias is ... else (alias if alias is not ... else None)
                next_category = current["category_override"] if current and category_override is ... else (category_override if category_override is not ... else None)
                next_note = current["note"] if current and note is ... else (note if note is not ... else None)
                next_favorite = bool(current["favorite"]) if current and favorite is ... else (bool(favorite) if favorite is not ... else False)
                next_location = current["location"] if current and location is ... else (location if location is not ... else None)
                if current and tags is ...:
                    try:
                        next_tags = [
                            str(value)
                            for value in json.loads(current["tags_json"] or "[]")
                            if str(value).strip()
                        ]
                    except (TypeError, ValueError):
                        next_tags = []
                elif tags is ...:
                    next_tags = []
                else:
                    next_tags = list(tags)
                connection.execute(
                    "INSERT INTO device_metadata(device_id, alias, category_override, note, favorite, location, tags_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(device_id) DO UPDATE SET alias=excluded.alias, category_override=excluded.category_override, "
                    "note=excluded.note, favorite=excluded.favorite, location=excluded.location, tags_json=excluded.tags_json, "
                    "updated_at=excluded.updated_at",
                    (
                        device_id, next_alias, next_category, next_note, int(next_favorite),
                        next_location, json.dumps(next_tags, separators=(",", ":")), now,
                    ),
                )
                if next_alias:
                    connection.execute(
                        "UPDATE device_events SET display_name = ? WHERE entity_id = ?",
                        (next_alias, device_id),
                    )
                if not next_favorite:
                    connection.execute(
                        "DELETE FROM device_watch_state WHERE device_id = ?",
                        (device_id,),
                    )
                connection.commit()
                return {
                    "alias": next_alias,
                    "category_override": next_category,
                    "note": next_note,
                    "favorite": next_favorite,
                    "location": next_location,
                    "tags": next_tags,
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
