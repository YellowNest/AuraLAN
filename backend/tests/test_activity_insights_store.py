import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.persistence.device_store import DeviceStore


class ActivityInsightStoreTests(unittest.TestCase):
    def test_activity_summary_and_daily_buckets_are_aggregate_only(self):
        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            device_store.readiness_check()
            now = 700000
            events = [
                ("device_first_seen", "device-a", now - 600),
                ("favorite_not_seen", "device-b", now - 1200),
                ("favorite_seen_again", "device-b", now - 1800),
                ("service_exposure_changed", "device-c", now - 3600),
                ("baseline_captured", "network", now - 90000),
                ("device_first_seen", "device-d", now - 3 * 86400),
                ("baseline_cleared", "network", now - 6 * 86400),
                ("device_first_seen", "too-old", now - 8 * 86400),
            ]

            connection = sqlite3.connect(device_store.path)
            try:
                for event_type, entity_id, created_at in events:
                    connection.execute(
                        "INSERT INTO device_events("
                        "event_type, entity_id, display_name, ip, mac, details_json, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            event_type,
                            entity_id,
                            "Private display name",
                            "192.0.2.10",
                            "02:00:00:00:00:10",
                            "{}",
                            created_at,
                        ),
                    )
                connection.commit()
            finally:
                connection.close()

            day = device_store.activity_summary_since(now - 86400)
            self.assertEqual(day["total"], 4)
            self.assertEqual(day["new_devices"], 1)
            self.assertEqual(day["watch_changes"], 2)
            self.assertEqual(day["service_changes"], 1)
            self.assertEqual(day["baseline_changes"], 0)

            week = device_store.activity_summary_since(now - 7 * 86400)
            self.assertEqual(week["total"], 7)
            self.assertEqual(week["new_devices"], 2)
            self.assertEqual(week["watch_changes"], 2)
            self.assertEqual(week["service_changes"], 1)
            self.assertEqual(week["baseline_changes"], 2)

            buckets = device_store.activity_daily_counts(7, now=now)
            self.assertEqual(len(buckets), 7)
            self.assertEqual(sum(item["total"] for item in buckets), 7)
            self.assertEqual(sum(item["new_devices"] for item in buckets), 2)
            self.assertEqual(sum(item["watch_changes"] for item in buckets), 2)
            self.assertEqual(sum(item["service_changes"] for item in buckets), 1)
            self.assertEqual(sum(item["baseline_changes"] for item in buckets), 2)

            rendered = repr({"day": day, "week": week, "buckets": buckets})
            self.assertNotIn("Private display name", rendered)
            self.assertNotIn("192.0.2.10", rendered)
            self.assertNotIn("02:00:00:00:00:10", rendered)


if __name__ == "__main__":
    unittest.main()
