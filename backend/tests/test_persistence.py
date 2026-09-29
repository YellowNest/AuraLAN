import os
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.persistence.device_store import (
    DeviceStore,
    default_data_dir,
    presence_missing_grace_seconds,
    watch_missing_grace_seconds,
)


class DefaultDataDirTests(unittest.TestCase):
    def test_explicit_data_dir_wins(self):
        with patch.dict(os.environ, {"AURALAN_DATA_DIR": "/tmp/auralan-state", "XDG_STATE_HOME": "/tmp/xdg"}, clear=True):
            self.assertEqual(default_data_dir(), Path("/tmp/auralan-state"))

    def test_xdg_state_home_is_used_for_user_processes(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": "/tmp/xdg-state"}, clear=True):
            self.assertEqual(default_data_dir(), Path("/tmp/xdg-state/auralan"))

    def test_home_state_directory_is_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "home", return_value=Path("/tmp/example-home")):
            self.assertEqual(default_data_dir(), Path("/tmp/example-home/.local/state/auralan"))

    def test_readiness_check_bootstraps_and_reopens_state(self):
        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            first = device_store.readiness_check()
            second = device_store.readiness_check()

            self.assertTrue(first["ready"])
            self.assertEqual(first["schema_version"], second["schema_version"])
            self.assertTrue((Path(temp_dir) / "auralan.db").is_file())

    def test_readiness_check_rejects_a_non_sqlite_database(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "auralan.db"
            path.write_text("not sqlite", encoding="utf-8")
            device_store = DeviceStore(Path(temp_dir))

            with self.assertRaises(sqlite3.DatabaseError):
                device_store.readiness_check()

    def test_schema_two_state_migrates_to_discovery_events(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auralan.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)")
                connection.execute("""CREATE TABLE device_metadata (
                    device_id TEXT PRIMARY KEY,
                    alias TEXT,
                    category_override TEXT,
                    note TEXT,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )""")
                connection.execute("""CREATE TABLE device_presence (
                    device_id TEXT PRIMARY KEY,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                )""")
                connection.execute("""CREATE TABLE device_identity_cache (
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
                connection.execute("PRAGMA user_version = 2")
                connection.commit()
            finally:
                connection.close()

            result = DeviceStore(Path(temp_dir)).readiness_check()
            self.assertTrue(result["ready"])
            self.assertEqual(result["schema_version"], 7)

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                connection.close()
            self.assertIn("device_events", tables)
            self.assertIn("device_inventory", tables)


    def test_schema_three_state_migrates_to_known_device_inventory(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auralan.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)")
                connection.execute("""CREATE TABLE device_metadata (
                    device_id TEXT PRIMARY KEY,
                    alias TEXT,
                    category_override TEXT,
                    note TEXT,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )""")
                connection.execute("""CREATE TABLE device_presence (
                    device_id TEXT PRIMARY KEY,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                )""")
                connection.execute("""CREATE TABLE device_identity_cache (
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
                connection.execute("""CREATE TABLE device_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    display_name TEXT,
                    ip TEXT,
                    mac TEXT,
                    created_at INTEGER NOT NULL
                )""")
                connection.execute("PRAGMA user_version = 3")
                connection.commit()
            finally:
                connection.close()

            result = DeviceStore(Path(temp_dir)).readiness_check()
            self.assertEqual(result["schema_version"], 7)

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                connection.close()
            self.assertIn("device_inventory", tables)



    def test_schema_four_state_migrates_to_watch_and_notification_tables(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auralan.db"
            device_store = DeviceStore(Path(temp_dir))
            device_store.readiness_check()

            connection = sqlite3.connect(db_path)
            try:
                connection.execute("DROP TABLE device_watch_state")
                connection.execute("DROP TABLE notification_cursors")
                connection.execute("PRAGMA user_version = 4")
                connection.commit()
            finally:
                connection.close()

            result = device_store.readiness_check()
            self.assertEqual(result["schema_version"], 7)

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                connection.close()

            self.assertIn("device_watch_state", tables)
            self.assertIn("notification_cursors", tables)

    def test_schema_five_adds_device_location_and_tags_without_losing_metadata(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "auralan.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)")
                connection.execute("""CREATE TABLE device_metadata (
                    device_id TEXT PRIMARY KEY,
                    alias TEXT,
                    category_override TEXT,
                    note TEXT,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )""")
                connection.execute("""CREATE TABLE device_presence (
                    device_id TEXT PRIMARY KEY,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                )""")
                connection.execute("""CREATE TABLE device_identity_cache (
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
                connection.execute("""CREATE TABLE device_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    display_name TEXT,
                    ip TEXT,
                    mac TEXT,
                    created_at INTEGER NOT NULL
                )""")
                connection.execute("""CREATE TABLE device_inventory (
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
                connection.execute("""CREATE TABLE device_watch_state (
                    device_id TEXT PRIMARY KEY,
                    not_seen INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )""")
                connection.execute("""CREATE TABLE notification_cursors (
                    channel TEXT PRIMARY KEY,
                    last_event_id INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )""")
                connection.execute(
                    "INSERT INTO device_metadata(device_id, alias, category_override, note, favorite, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("001122334455", "Printer", "printer", "Upstairs", 1, 100),
                )
                connection.execute("PRAGMA user_version = 5")
                connection.commit()
            finally:
                connection.close()

            device_store = DeviceStore(Path(temp_dir))
            result = device_store.readiness_check()
            self.assertEqual(result["schema_version"], 7)

            enriched = device_store.enrich(["001122334455"])["001122334455"]
            self.assertEqual(enriched["alias"], "Printer")
            self.assertEqual(enriched["note"], "Upstairs")
            self.assertEqual(enriched["favorite"], 1)
            self.assertIsNone(enriched["location"])
            self.assertEqual(enriched["tags"], [])

    def test_schema_six_adds_presence_history_tables_without_touching_existing_state(self):
        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            device_store.readiness_check()

            db_path = Path(temp_dir) / "auralan.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("DROP TABLE device_presence_state")
                connection.execute("DROP TABLE device_presence_history")
                connection.execute("PRAGMA user_version = 6")
                connection.commit()
            finally:
                connection.close()

            result = device_store.readiness_check()
            self.assertEqual(result["schema_version"], 7)

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                connection.close()

            self.assertIn("device_presence_state", tables)
            self.assertIn("device_presence_history", tables)

    def test_presence_history_debounces_absence_and_records_return(self):
        with TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"AURALAN_PRESENCE_MISSING_GRACE": "180"},
            clear=False,
        ):
            device_store = DeviceStore(Path(temp_dir))
            device = {
                "id": "001122334455",
                "display_name": "Laptop",
                "state": "online",
            }

            with patch("app.persistence.device_store.time.time", return_value=1000):
                device_store.record_presence_transitions([device])
            self.assertEqual(device_store.presence_history(device["id"]), [])

            device["state"] = "known"
            with patch("app.persistence.device_store.time.time", return_value=1060):
                device_store.record_presence_transitions([device])
            with patch("app.persistence.device_store.time.time", return_value=1180):
                device_store.record_presence_transitions([device])
            self.assertEqual(device_store.presence_history(device["id"]), [])

            with patch("app.persistence.device_store.time.time", return_value=1240):
                device_store.record_presence_transitions([device])

            history = device_store.presence_history(device["id"])
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["event_type"], "device_not_seen")

            device["state"] = "online"
            with patch("app.persistence.device_store.time.time", return_value=1300):
                device_store.record_presence_transitions([device])

            history = device_store.presence_history(device["id"])
            self.assertEqual(
                [item["event_type"] for item in history],
                ["device_seen_again", "device_not_seen"],
            )

    def test_transient_presence_gap_is_not_persisted(self):
        with TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"AURALAN_PRESENCE_MISSING_GRACE": "180"},
            clear=False,
        ):
            device_store = DeviceStore(Path(temp_dir))
            device = {"id": "001122334455", "display_name": "Laptop", "state": "online"}

            with patch("app.persistence.device_store.time.time", return_value=1000):
                device_store.record_presence_transitions([device])

            device["state"] = "known"
            with patch("app.persistence.device_store.time.time", return_value=1060):
                device_store.record_presence_transitions([device])

            device["state"] = "online"
            with patch("app.persistence.device_store.time.time", return_value=1100):
                device_store.record_presence_transitions([device])

            self.assertEqual(device_store.presence_history(device["id"]), [])

    def test_presence_history_limit_and_grace_configuration_are_bounded(self):
        with patch.dict(os.environ, {"AURALAN_PRESENCE_MISSING_GRACE": "0"}, clear=False):
            self.assertEqual(presence_missing_grace_seconds(), 0)
        with patch.dict(os.environ, {"AURALAN_PRESENCE_MISSING_GRACE": "-1"}, clear=False):
            self.assertEqual(presence_missing_grace_seconds(), 0)
        with patch.dict(os.environ, {"AURALAN_PRESENCE_MISSING_GRACE": "999999"}, clear=False):
            self.assertEqual(presence_missing_grace_seconds(), 86400)
        with patch.dict(os.environ, {"AURALAN_PRESENCE_MISSING_GRACE": "bad"}, clear=False):
            self.assertEqual(presence_missing_grace_seconds(), 180)

        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            device = {"id": "001122334455", "display_name": "Laptop", "state": "online"}
            with patch.dict(os.environ, {"AURALAN_PRESENCE_MISSING_GRACE": "0"}, clear=False):
                with patch("app.persistence.device_store.time.time", return_value=1000):
                    device_store.record_presence_transitions([device])
                for index in range(3):
                    device["state"] = "known"
                    with patch("app.persistence.device_store.time.time", return_value=1100 + index * 20):
                        device_store.record_presence_transitions([device])
                    device["state"] = "online"
                    with patch("app.persistence.device_store.time.time", return_value=1110 + index * 20):
                        device_store.record_presence_transitions([device])

            self.assertEqual(len(device_store.presence_history(device["id"], 2)), 2)

    def test_favorite_watch_absence_is_debounced_and_return_is_immediate(self):
        with TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"AURALAN_WATCH_MISSING_GRACE": "120"},
            clear=False,
        ):
            device_store = DeviceStore(Path(temp_dir))
            device = {
                "id": "001122334455",
                "display_name": "Front door camera",
                "ip": "192.0.2.80",
                "mac": "00:11:22:33:44:55",
                "state": "online",
                "metadata": {"favorite": True},
            }

            with patch("app.persistence.device_store.time.time", return_value=1000):
                device_store.record_watch_transitions([device])
            self.assertEqual(device_store.recent_events(), [])

            device["state"] = "known"
            with patch("app.persistence.device_store.time.time", return_value=1060):
                device_store.record_watch_transitions([device])
            with patch("app.persistence.device_store.time.time", return_value=1120):
                device_store.record_watch_transitions([device])
            self.assertEqual(device_store.recent_events(), [])

            with patch("app.persistence.device_store.time.time", return_value=1180):
                device_store.record_watch_transitions([device])

            events = device_store.recent_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "favorite_not_seen")

            with patch("app.persistence.device_store.time.time", return_value=1240):
                device_store.record_watch_transitions([device])
            self.assertEqual(len(device_store.recent_events()), 1)

            device["state"] = "online"
            with patch("app.persistence.device_store.time.time", return_value=1300):
                device_store.record_watch_transitions([device])

            events = device_store.recent_events()
            self.assertEqual([event["event_type"] for event in events], [
                "favorite_seen_again",
                "favorite_not_seen",
            ])

    def test_transient_favorite_discovery_gap_does_not_create_event(self):
        with TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"AURALAN_WATCH_MISSING_GRACE": "120"},
            clear=False,
        ):
            device_store = DeviceStore(Path(temp_dir))
            device = {
                "id": "001122334455",
                "display_name": "Front door camera",
                "state": "online",
                "metadata": {"favorite": True},
            }

            with patch("app.persistence.device_store.time.time", return_value=1000):
                device_store.record_watch_transitions([device])

            device["state"] = "known"
            with patch("app.persistence.device_store.time.time", return_value=1060):
                device_store.record_watch_transitions([device])

            device["state"] = "online"
            with patch("app.persistence.device_store.time.time", return_value=1100):
                device_store.record_watch_transitions([device])

            self.assertEqual(device_store.recent_events(), [])

    def test_watch_missing_grace_configuration_is_safe(self):
        with patch.dict(os.environ, {"AURALAN_WATCH_MISSING_GRACE": "0"}, clear=False):
            self.assertEqual(watch_missing_grace_seconds(), 0)
        with patch.dict(os.environ, {"AURALAN_WATCH_MISSING_GRACE": "-10"}, clear=False):
            self.assertEqual(watch_missing_grace_seconds(), 0)
        with patch.dict(os.environ, {"AURALAN_WATCH_MISSING_GRACE": "999999"}, clear=False):
            self.assertEqual(watch_missing_grace_seconds(), 86400)
        with patch.dict(os.environ, {"AURALAN_WATCH_MISSING_GRACE": "invalid"}, clear=False):
            self.assertEqual(watch_missing_grace_seconds(), 120)

    def test_notification_cursor_and_ordered_event_query(self):
        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            metadata = device_store.enrich(["001122334455"])["001122334455"]
            record = {
                "id": "001122334455",
                "display_name": "Sample device",
                "ip": "192.0.2.50",
                "mac": "00:11:22:33:44:55",
                "mac_addresses": ["00:11:22:33:44:55"],
                "first_seen_at": metadata["first_seen_at"],
            }
            device_store.record_first_seen([record], {"001122334455"})

            latest = device_store.latest_event_id()
            self.assertGreater(latest, 0)
            self.assertIsNone(device_store.notification_cursor("webhook"))
            self.assertEqual(device_store.events_after(0)[0]["id"], latest)

            device_store.set_notification_cursor("webhook", latest)
            self.assertEqual(device_store.notification_cursor("webhook"), latest)
            self.assertEqual(device_store.events_after(latest), [])


    def test_remembered_devices_survive_current_discovery_and_do_not_duplicate_live_macs(self):
        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            metadata = device_store.enrich(["001122334455"])["001122334455"]
            record = {
                "id": "001122334455",
                "display_name": "Office printer",
                "hostname": "office-printer",
                "vendor": "Example",
                "model": "Laser 1",
                "device_type": "printer",
                "category": "printer",
                "icon_key": "printer",
                "ip": "192.0.2.70",
                "ip_addresses": ["192.0.2.70"],
                "mac": "00:11:22:33:44:55",
                "mac_addresses": ["00:11:22:33:44:55"],
                "mac_type": "global",
                "interface": "lan0",
                "connection_type": "ethernet",
                "online": True,
                "state": "online",
                "first_seen_at": metadata["first_seen_at"],
                "last_seen_at": metadata["last_seen_at"],
                "identity": {
                    "display_name": {"value": "Office printer", "source": "local_hosts", "confidence": "high"},
                    "vendor": {"value": "Example", "source": "oui_vendor", "confidence": "high"},
                    "model": {"value": "Laser 1", "source": "dns_sd", "confidence": "medium"},
                    "device_type": {"value": "printer", "source": "dns_sd", "confidence": "medium"},
                    "sources": [],
                },
                "metadata": {"alias": None, "category_override": None, "note": None, "favorite": False},
                "observations": [],
            }

            device_store.remember_inventory([record])

            backfilled_events = device_store.recent_events()
            self.assertEqual(len(backfilled_events), 1)
            self.assertEqual(backfilled_events[0]["event_type"], "device_first_seen")
            self.assertEqual(backfilled_events[0]["entity_id"], "001122334455")
            self.assertEqual(backfilled_events[0]["created_at"], metadata["first_seen_at"])

            remembered = device_store.known_devices([])
            self.assertEqual(len(remembered), 1)
            self.assertEqual(remembered[0]["state"], "known")
            self.assertIsNone(remembered[0]["online"])
            self.assertEqual(remembered[0]["display_name"], "Office printer")
            self.assertEqual(remembered[0]["ip"], "192.0.2.70")
            self.assertEqual(remembered[0]["last_seen_at"], metadata["last_seen_at"])

            live_same_mac = [{"id": "different-primary", "mac_addresses": ["00:11:22:33:44:55"]}]
            self.assertEqual(device_store.known_devices(live_same_mac), [])

            device_store.update_metadata(
                "001122334455",
                alias="Printer",
                note="Upstairs",
                favorite=True,
            )
            remembered = device_store.known_devices([])
            self.assertEqual(remembered[0]["metadata"]["alias"], "Printer")
            self.assertEqual(remembered[0]["metadata"]["note"], "Upstairs")
            self.assertTrue(remembered[0]["metadata"]["favorite"])


    def test_first_seen_events_are_persistent_deduplicated_and_follow_aliases(self):
        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            metadata = device_store.enrich(["001122334455"])
            self.assertTrue(metadata["001122334455"]["_new_presence"])

            record = {
                "id": "001122334455",
                "display_name": "Sample device",
                "ip": "192.0.2.50",
                "mac": "00:11:22:33:44:55",
                "mac_addresses": ["00:11:22:33:44:55"],
                "first_seen_at": metadata["001122334455"]["first_seen_at"],
            }
            device_store.record_first_seen([record], {"001122334455"})
            device_store.record_first_seen([record], {"001122334455"})

            events = device_store.recent_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "device_first_seen")
            self.assertEqual(events[0]["display_name"], "Sample device")
            self.assertEqual(events[0]["ip"], "192.0.2.50")

            device_store.update_metadata("001122334455", alias="Kitchen sensor")
            self.assertEqual(device_store.recent_events()[0]["display_name"], "Kitchen sensor")


    def test_inventory_metadata_round_trips_and_partial_updates_preserve_fields(self):
        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            saved = device_store.update_metadata(
                "001122334455",
                alias="Office printer",
                category_override="printer",
                note="Upstairs",
                favorite=True,
                location="Office",
                tags=["infrastructure", "laser"],
            )
            self.assertEqual(saved["note"], "Upstairs")
            self.assertTrue(saved["favorite"])
            self.assertEqual(saved["location"], "Office")
            self.assertEqual(saved["tags"], ["infrastructure", "laser"])

            enriched = device_store.enrich(["001122334455"])["001122334455"]
            self.assertEqual(enriched["alias"], "Office printer")
            self.assertEqual(enriched["category_override"], "printer")
            self.assertEqual(enriched["note"], "Upstairs")
            self.assertEqual(enriched["favorite"], 1)
            self.assertEqual(enriched["location"], "Office")
            self.assertEqual(enriched["tags"], ["infrastructure", "laser"])
            self.assertIsNotNone(enriched["first_seen_at"])
            self.assertIsNotNone(enriched["last_seen_at"])

            device_store.update_metadata("001122334455", alias="Printer")
            preserved = device_store.enrich(["001122334455"])["001122334455"]
            self.assertEqual(preserved["alias"], "Printer")
            self.assertEqual(preserved["note"], "Upstairs")
            self.assertEqual(preserved["favorite"], 1)
            self.assertEqual(preserved["location"], "Office")
            self.assertEqual(preserved["tags"], ["infrastructure", "laser"])


if __name__ == "__main__":
    unittest.main()
