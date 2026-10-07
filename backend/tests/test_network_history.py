import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.persistence.device_store import DeviceStore, NETWORK_HISTORY_BUCKET_SECONDS


def snapshot(*, current=2, remembered=1, offline_services=0, errors=0, state="healthy"):
    devices = [
        {
            "id": f"current-{index}",
            "display_name": f"Private device {index}",
            "ip": f"192.0.2.{10 + index}",
            "mac": f"02:00:00:00:00:{index:02X}",
            "state": "online",
            "online": True,
            "metadata": {"note": "private"},
        }
        for index in range(current)
    ]
    devices.extend(
        {
            "id": f"remembered-{index}",
            "display_name": f"Remembered {index}",
            "ip": f"192.0.2.{100 + index}",
            "mac": f"02:00:00:00:01:{index:02X}",
            "state": "known",
            "online": None,
            "metadata": {"location": "Private room"},
        }
        for index in range(remembered)
    )
    services = [
        {
            "id": f"service-{index}",
            "detected": True,
            "state": "offline" if index < offline_services else "online",
        }
        for index in range(max(2, offline_services))
    ]
    return {
        "system": {"state": state},
        "devices": devices,
        "services": {"items": services},
        "errors": [f"error-{index}" for index in range(errors)],
    }


class NetworkHistoryStoreTests(unittest.TestCase):
    def test_history_coalesces_monitor_passes_inside_one_bucket(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            first = 1_800_000
            second = first + 60

            store.record_network_snapshot(snapshot(current=2), now=first)
            store.record_network_snapshot(snapshot(current=3, remembered=2), now=second)

            history = store.network_history(24, now=second)

        self.assertEqual(len(history["items"]), 1)
        sample = history["items"][0]
        self.assertEqual(sample["bucket_start"], first - (first % NETWORK_HISTORY_BUCKET_SECONDS))
        self.assertEqual(sample["sample_count"], 2)
        self.assertEqual(sample["current_devices"], 3)
        self.assertEqual(sample["online_devices"], 3)
        self.assertEqual(sample["remembered_devices"], 2)

    def test_history_is_aggregate_only_and_tracks_service_health(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            now = 2_000_000
            store.record_network_snapshot(
                snapshot(current=4, remembered=2, offline_services=1, errors=2, state="degraded"),
                now=now,
            )

            history = store.network_history(24, now=now)
            rendered = repr(history)

        sample = history["items"][0]
        self.assertEqual(sample["services_detected"], 2)
        self.assertEqual(sample["services_offline"], 1)
        self.assertEqual(sample["discovery_errors"], 2)
        self.assertEqual(sample["system_state"], "degraded")
        for private_value in (
            "Private device",
            "Remembered",
            "192.0.2.",
            "02:00:00",
            "Private room",
            "private",
        ):
            self.assertNotIn(private_value, rendered)

    def test_history_window_is_bounded_and_schema_is_versioned(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            now = 3_000_000
            old = now - (25 * 60 * 60)
            store.record_network_snapshot(snapshot(current=1), now=old)
            store.record_network_snapshot(snapshot(current=5), now=now)

            last_day = store.network_history(24, now=now)
            capped = store.network_history(9999, now=now)

            connection = sqlite3.connect(store.path)
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                connection.close()

        self.assertEqual(len(last_day["items"]), 1)
        self.assertEqual(last_day["items"][0]["current_devices"], 5)
        self.assertEqual(capped["window_hours"], 720)
        self.assertIn("network_history", tables)
        self.assertGreaterEqual(version, 11)

    def test_schema_ten_upgrades_to_network_history_without_losing_metadata(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            store.readiness_check()
            store.update_metadata("001122334455", alias="Preserved device")

            connection = sqlite3.connect(store.path)
            try:
                connection.execute("DROP TABLE network_history")
                connection.execute("PRAGMA user_version = 10")
                connection.commit()
            finally:
                connection.close()

            result = store.readiness_check()
            metadata = store.enrich(["001122334455"])["001122334455"]

            connection = sqlite3.connect(store.path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                connection.close()

        self.assertTrue(result["ready"])
        self.assertEqual(result["schema_version"], 11)
        self.assertEqual(metadata["alias"], "Preserved device")
        self.assertIn("network_history", tables)


if __name__ == "__main__":
    unittest.main()
