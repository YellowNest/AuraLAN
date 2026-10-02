from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.persistence.device_store import DeviceStore, SCHEMA_VERSION


class ServiceScanStoreTests(unittest.TestCase):
    def test_service_scan_history_persists_and_diffs_previous_snapshot(self):
        with TemporaryDirectory() as temp_dir:
            store = DeviceStore(Path(temp_dir))

            first = store.record_service_scan(
                "001122334455",
                "192.0.2.40",
                [443, 22],
                checked_at=1000,
            )
            self.assertFalse(first["changed"])
            self.assertIsNone(first["previous_checked_at"])
            self.assertEqual(first["newly_open"], [])
            self.assertEqual(first["no_longer_open"], [])

            second = store.record_service_scan(
                "001122334455",
                "192.0.2.40",
                [443, 8123],
                checked_at=1100,
                display_name="Example server",
            )
            self.assertTrue(second["changed"])
            self.assertEqual(second["previous_checked_at"], 1000)
            self.assertEqual(second["newly_open"], [8123])
            self.assertEqual(second["no_longer_open"], [22])

            history = store.service_scan_history("001122334455")
            self.assertEqual([item["checked_at"] for item in history], [1100, 1000])
            self.assertEqual(history[0]["open_ports"], [443, 8123])
            self.assertEqual(history[1]["open_ports"], [22, 443])

            events = store.recent_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "service_exposure_changed")
            self.assertEqual(events[0]["entity_id"], "001122334455")
            self.assertEqual(events[0]["display_name"], "Example server")
            self.assertEqual(events[0]["details"]["newly_open"], [8123])
            self.assertEqual(events[0]["details"]["no_longer_open"], [22])

    def test_schema_eight_migrates_to_service_scan_table_without_losing_state(self):
        with TemporaryDirectory() as temp_dir:
            store = DeviceStore(Path(temp_dir))
            store.readiness_check()
            store.update_metadata("001122334455", alias="Example device")

            db_path = Path(temp_dir) / "auralan.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("DROP INDEX idx_device_service_scans_device_time")
                connection.execute("DROP TABLE device_service_scans")
                connection.execute("PRAGMA user_version = 8")
                connection.commit()
            finally:
                connection.close()

            result = store.readiness_check()
            self.assertEqual(result["schema_version"], SCHEMA_VERSION)
            enriched = store.enrich(["001122334455"])["001122334455"]
            self.assertEqual(enriched["alias"], "Example device")

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                indexes = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                }
            finally:
                connection.close()

            self.assertIn("device_service_scans", tables)
            self.assertIn("idx_device_service_scans_device_time", indexes)

    def test_forgetting_device_removes_service_scan_history(self):
        with TemporaryDirectory() as temp_dir:
            store = DeviceStore(Path(temp_dir))
            store.enrich(["001122334455"])
            store.record_service_scan(
                "001122334455",
                "192.0.2.40",
                [22],
                checked_at=1000,
            )

            self.assertTrue(store.forget_device("001122334455"))
            self.assertEqual(store.service_scan_history("001122334455"), [])


if __name__ == "__main__":
    unittest.main()
