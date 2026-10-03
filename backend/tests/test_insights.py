import unittest

from app.insights import build_network_insights


class NetworkInsightsTests(unittest.TestCase):
    def test_builds_attention_state_and_aggregate_counts(self):
        snapshot = {
            "devices": [
                {
                    "id": "router",
                    "hostname": "router",
                    "vendor": "Example",
                    "category": "router",
                    "online": True,
                    "state": "online",
                    "first_seen_at": 100,
                    "identity": {
                        "display_name": {"confidence": "high"},
                        "device_type": {"confidence": "high"},
                        "sources": [{"confidence": "high"}],
                    },
                    "metadata": {"favorite": True},
                },
                {
                    "id": "new-device",
                    "hostname": None,
                    "vendor": None,
                    "model": None,
                    "category": "unknown",
                    "online": True,
                    "state": "online",
                    "first_seen_at": 199900,
                    "identity": {"sources": []},
                    "metadata": {"favorite": False},
                },
                {
                    "id": "remembered",
                    "hostname": "old-laptop",
                    "vendor": "Example",
                    "category": "computer",
                    "online": None,
                    "state": "known",
                    "first_seen_at": 100,
                    "identity": {
                        "display_name": {"confidence": "medium"},
                        "device_type": {"confidence": "medium"},
                        "sources": [{"confidence": "medium"}],
                    },
                    "metadata": {"favorite": True},
                },
            ],
            "services": {
                "items": [
                    {"detected": True, "state": "online"},
                    {"detected": True, "state": "offline"},
                    {"detected": False, "state": "unknown"},
                ],
            },
            "errors": ["provider unavailable"],
        }
        baseline = {"new_count": 1, "missing_count": 1}
        activity_24h = {
            "total": 3,
            "new_devices": 1,
            "watch_changes": 1,
            "service_changes": 1,
            "baseline_changes": 0,
        }
        activity_7d = {
            "total": 8,
            "new_devices": 2,
            "watch_changes": 2,
            "service_changes": 2,
            "baseline_changes": 2,
        }
        days = [{"start_at": 100, "total": 2}]

        result = build_network_insights(
            snapshot,
            baseline,
            activity_24h,
            activity_7d,
            days,
            now=200000,
        )

        self.assertEqual(result["state"], "attention")
        self.assertEqual(result["current_devices"], 2)
        self.assertEqual(result["remembered_devices"], 1)
        self.assertEqual(result["online_devices"], 2)
        self.assertEqual(result["identity_needs_review"], 1)
        self.assertEqual(result["favorites_total"], 2)
        self.assertEqual(result["favorites_not_seen_now"], 1)
        self.assertEqual(result["new_devices_24h"], 1)
        self.assertEqual(result["baseline_new"], 1)
        self.assertEqual(result["baseline_missing"], 1)
        self.assertEqual(result["services_detected"], 2)
        self.assertEqual(result["services_offline"], 1)
        self.assertEqual(result["discovery_errors"], 1)
        self.assertEqual(result["attention_count"], 4)
        self.assertEqual(result["activity_24h"]["service_changes"], 1)
        self.assertEqual(result["activity_7d"]["total"], 8)

    def test_quiet_state_contains_no_device_identity_values(self):
        snapshot = {
            "devices": [{
                "id": "private-id",
                "display_name": "Private Phone",
                "hostname": "private-phone",
                "vendor": "Example",
                "model": "Secret Model",
                "category": "phone",
                "online": True,
                "state": "online",
                "first_seen_at": 1,
                "identity": {
                    "display_name": {"confidence": "high"},
                    "device_type": {"confidence": "high"},
                    "sources": [{"confidence": "high"}],
                },
                "metadata": {
                    "favorite": False,
                    "alias": "Private alias",
                    "location": "Bedroom",
                    "note": "Secret note",
                },
            }],
            "services": {"items": []},
            "errors": [],
        }
        empty = {
            "total": 0,
            "new_devices": 0,
            "watch_changes": 0,
            "service_changes": 0,
            "baseline_changes": 0,
        }

        result = build_network_insights(
            snapshot,
            {"new_count": 0, "missing_count": 0},
            empty,
            empty,
            [],
            now=200000,
        )

        self.assertEqual(result["state"], "quiet")
        rendered = repr(result)
        for value in (
            "private-id",
            "Private Phone",
            "private-phone",
            "Secret Model",
            "Private alias",
            "Bedroom",
            "Secret note",
        ):
            self.assertNotIn(value, rendered)


if __name__ == "__main__":
    unittest.main()
