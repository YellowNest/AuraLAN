import os
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.persistence.device_store import DeviceStore, default_data_dir


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
            self.assertEqual(result["schema_version"], 4)

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
            self.assertEqual(result["schema_version"], 4)

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                connection.close()
            self.assertIn("device_inventory", tables)



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
            )
            self.assertEqual(saved["note"], "Upstairs")
            self.assertTrue(saved["favorite"])

            enriched = device_store.enrich(["001122334455"])["001122334455"]
            self.assertEqual(enriched["alias"], "Office printer")
            self.assertEqual(enriched["category_override"], "printer")
            self.assertEqual(enriched["note"], "Upstairs")
            self.assertEqual(enriched["favorite"], 1)
            self.assertIsNotNone(enriched["first_seen_at"])
            self.assertIsNotNone(enriched["last_seen_at"])

            device_store.update_metadata("001122334455", alias="Printer")
            preserved = device_store.enrich(["001122334455"])["001122334455"]
            self.assertEqual(preserved["alias"], "Printer")
            self.assertEqual(preserved["note"], "Upstairs")
            self.assertEqual(preserved["favorite"], 1)


if __name__ == "__main__":
    unittest.main()
