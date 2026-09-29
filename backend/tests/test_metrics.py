import unittest
from unittest.mock import patch

from app.main import metrics
from app.metrics import render_prometheus


class PrometheusMetricsTests(unittest.TestCase):
    def snapshot(self):
        return {
            "devices": [
                {
                    "id": "private-device-id",
                    "display_name": "Secret camera",
                    "ip": "192.0.2.10",
                    "mac": "02:00:00:00:00:10",
                    "state": "online",
                    "online": True,
                    "metadata": {"note": "Do not export this to metrics"},
                },
                {
                    "id": "remembered-device-id",
                    "display_name": "Old tablet",
                    "ip": "192.0.2.11",
                    "mac": "02:00:00:00:00:11",
                    "state": "known",
                    "online": None,
                    "metadata": {},
                },
            ],
            "services": {
                "items": [
                    {"id": "docker", "detected": True, "state": "online"},
                    {"id": "pihole", "detected": True, "state": "offline"},
                    {"id": "caddy", "detected": False, "state": "unknown"},
                ],
            },
            "host": {
                "memory_used_percent": 42,
                "storage_used_percent": 61,
                "temperature_celsius": 51.5,
            },
            "errors": ["example warning"],
        }

    def test_metrics_are_aggregate_and_omit_device_identity(self):
        rendered = render_prometheus(self.snapshot())

        self.assertIn("auralan_up 1", rendered)
        self.assertIn("auralan_devices_total 2", rendered)
        self.assertIn("auralan_devices_current 1", rendered)
        self.assertIn("auralan_devices_online 1", rendered)
        self.assertIn("auralan_devices_not_seen_now 1", rendered)
        self.assertIn("auralan_services_detected 2", rendered)
        self.assertIn("auralan_services_online 1", rendered)
        self.assertIn("auralan_discovery_errors 1", rendered)
        self.assertIn("auralan_host_temperature_celsius 51.5", rendered)

        for private_value in (
            "Secret camera",
            "Old tablet",
            "192.0.2.10",
            "02:00:00:00:00:10",
            "Do not export this to metrics",
            "private-device-id",
        ):
            self.assertNotIn(private_value, rendered)

    def test_missing_optional_host_metrics_are_omitted(self):
        snapshot = self.snapshot()
        snapshot["host"]["temperature_celsius"] = None
        rendered = render_prometheus(snapshot)

        self.assertNotIn("auralan_host_temperature_celsius", rendered)

    def test_http_endpoint_uses_prometheus_text_format(self):
        with patch("app.main.system_snapshot", return_value=self.snapshot()):
            response = metrics()

        self.assertIn("text/plain", response.media_type)
        self.assertIn(b"auralan_devices_total 2", response.body)


if __name__ == "__main__":
    unittest.main()
