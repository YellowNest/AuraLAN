from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.persistence.device_store import DeviceStore


def device(device_id: str, macs: list[str], *, state: str = "online", name: str = "Device") -> dict:
    return {
        "id": device_id,
        "display_name": name,
        "state": state,
        "mac": macs[0] if macs else "—",
        "mac_addresses": macs,
    }


class NetworkBaselineTests(unittest.TestCase):
    def test_capture_uses_only_currently_observed_devices(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            status = store.capture_baseline([
                device("a", ["02:00:00:00:00:01"], name="Current"),
                device("b", ["02:00:00:00:00:02"], state="known", name="Remembered"),
            ])

        self.assertTrue(status["configured"])
        self.assertEqual(status["device_count"], 1)
        self.assertEqual(status["current_count"], 1)
        self.assertEqual(status["new_count"], 0)
        self.assertEqual(status["missing_count"], 0)

        events = store.recent_events()
        self.assertEqual(events[0]["event_type"], "baseline_captured")
        self.assertEqual(events[0]["entity_id"], "network")
        self.assertEqual(events[0]["details"]["device_count"], 1)

    def test_baseline_matches_any_known_mac_for_multi_interface_device(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            store.capture_baseline([
                device("primary-a", ["02:00:00:00:00:11", "02:00:00:00:00:12"]),
            ])

            status = store.baseline_status([
                device("primary-b", ["02:00:00:00:00:12", "02:00:00:00:00:11"]),
            ])

        self.assertEqual(status["new_count"], 0)
        self.assertEqual(status["missing_count"], 0)

    def test_baseline_reports_new_and_missing_devices_without_security_claims(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            store.capture_baseline([
                device("baseline-a", ["02:00:00:00:00:21"], name="First"),
                device("baseline-b", ["02:00:00:00:00:22"], name="Second"),
            ])

            status = store.baseline_status([
                device("baseline-a", ["02:00:00:00:00:21"], name="First"),
                device("new-c", ["02:00:00:00:00:23"], name="Third"),
                device("baseline-b", ["02:00:00:00:00:22"], state="known", name="Second"),
            ])

        self.assertEqual(status["new_device_ids"], ["new-c"])
        self.assertEqual(status["missing_device_ids"], ["baseline-b"])
        self.assertEqual(status["new_count"], 1)
        self.assertEqual(status["missing_count"], 1)

    def test_clear_baseline_returns_to_unconfigured_state(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            records = [device("a", ["02:00:00:00:00:31"])]
            store.capture_baseline(records)
            store.clear_baseline()
            status = store.baseline_status(records)

        self.assertFalse(status["configured"])
        self.assertEqual(status["device_count"], 0)

        events = store.recent_events()
        self.assertEqual([event["event_type"] for event in events[:2]], ["baseline_cleared", "baseline_captured"])
        self.assertEqual(events[0]["details"]["device_count"], 1)


if __name__ == "__main__":
    unittest.main()
