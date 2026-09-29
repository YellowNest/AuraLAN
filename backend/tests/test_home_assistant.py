import unittest

from app.home_assistant import home_assistant_summary


class HomeAssistantSummaryTests(unittest.TestCase):
    def test_summary_counts_devices_services_and_runtime_state(self):
        snapshot = {
            "generated_at": "2026-09-29T19:00:00+02:00",
            "system": {"state": "degraded", "attention_count": 2},
            "devices": [
                {
                    "display_name": "Laptop",
                    "ip": "192.0.2.10",
                    "mac": "00:11:22:33:44:55",
                    "online": True,
                    "state": "online",
                    "first_seen_at": 1900,
                    "metadata": {"favorite": True},
                },
                {
                    "display_name": "Camera",
                    "ip": "192.0.2.11",
                    "mac": "00:11:22:33:44:66",
                    "online": False,
                    "state": "known",
                    "first_seen_at": 100,
                    "metadata": {"favorite": True},
                },
                {
                    "display_name": "Speaker",
                    "online": None,
                    "state": "recently_seen",
                    "first_seen_at": 1950,
                    "metadata": {"favorite": False},
                },
            ],
            "services": {
                "items": [
                    {"name": "Docker", "detected": True, "state": "online"},
                    {"name": "Pi-hole", "detected": True, "state": "offline"},
                    {"name": "Caddy", "detected": False, "state": "unknown"},
                ]
            },
            "errors": ["provider unavailable"],
        }

        result = home_assistant_summary(
            snapshot,
            version="0.6.0-dev",
            api_version="v1",
            monitor={"running": True, "last_success_at": 1999},
            notifications={"configured": True, "pending_events": 3},
            wake_on_lan_enabled=False,
            now=2000,
        )

        self.assertEqual(result["devices_total"], 3)
        self.assertEqual(result["devices_online"], 1)
        self.assertEqual(result["devices_not_seen_now"], 1)
        self.assertEqual(result["favorites_total"], 2)
        self.assertEqual(result["favorites_not_seen_now"], 1)
        self.assertEqual(result["new_devices_24h"], 3)
        self.assertEqual(result["services_detected"], 2)
        self.assertEqual(result["services_online"], 1)
        self.assertEqual(result["discovery_errors"], 1)
        self.assertEqual(result["system_state"], "degraded")
        self.assertEqual(result["attention_count"], 2)
        self.assertTrue(result["monitor_running"])
        self.assertTrue(result["webhook_configured"])
        self.assertEqual(result["webhook_pending_events"], 3)
        self.assertFalse(result["wake_on_lan_enabled"])

    def test_summary_is_aggregate_only_and_omits_device_identity(self):
        snapshot = {
            "generated_at": "2026-09-29T19:00:00+02:00",
            "system": {"state": "healthy", "attention_count": 0},
            "devices": [{
                "id": "secret-device-id",
                "display_name": "Private phone name",
                "ip": "192.0.2.20",
                "mac": "00:11:22:33:44:77",
                "online": True,
                "state": "online",
                "first_seen_at": 100,
                "metadata": {
                    "favorite": True,
                    "note": "private note",
                    "location": "Bedroom",
                    "tags": ["private-tag"],
                },
            }],
            "services": {"items": []},
            "errors": [],
        }

        result = home_assistant_summary(
            snapshot,
            version="0.6.0-dev",
            api_version="v1",
            monitor={},
            notifications={},
            wake_on_lan_enabled=True,
            now=200000,
        )

        rendered = repr(result)
        for private_value in (
            "secret-device-id",
            "Private phone name",
            "192.0.2.20",
            "00:11:22:33:44:77",
            "private note",
            "Bedroom",
            "private-tag",
        ):
            self.assertNotIn(private_value, rendered)

        self.assertEqual(result["favorites_total"], 1)
        self.assertTrue(result["wake_on_lan_enabled"])


if __name__ == "__main__":
    unittest.main()
