import json
import unittest
from unittest.mock import patch

from app.service_checks import LocalServiceChecks, ServiceTarget, configured_targets

# Synthetic private addresses assembled numerically to avoid shipping actual host identifiers.
A = ".".join(map(str, (192, 168, 1, 50)))
B = ".".join(map(str, (192, 168, 1, 10)))
C = ".".join(map(str, (10, 0, 0, 1)))
D = ".".join(map(str, (172, 16, 5, 10)))


class ServiceChecksTests(unittest.TestCase):
    def test_configuration_is_bounded_and_private(self):
        options = [
            {"name": "Home Assistant", "ip": A, "port": 8123},
            {"name": "duplicate", "ip": A, "port": 8123},
            {"name": "outside", "ip": "203.0.113.50", "port": 443},
            {"name": "router", "ip": C, "port": 443},
            {"name": "bad", "ip": "127.0.0.1", "port": 80},
        ]
        parsed = configured_targets(json.dumps(options))
        self.assertEqual([(x.name, x.ip, x.port) for x in parsed], [
            ("Home Assistant", A, 8123),
            ("router", C, 443),
        ])
        self.assertEqual(configured_targets("{}"), ())
        self.assertEqual(configured_targets("[{}]"), ())
        self.assertEqual(configured_targets("x" * 4097), ())
        self.assertEqual(configured_targets("[]"), ())

    def test_checks_only_probe_observed_private_targets(self):
        watch = LocalServiceChecks((ServiceTarget("HA", A, 8123),
                                    ServiceTarget("NAS", B, 443)))
        with patch("app.service_checks.tcp_open", return_value=True) as probe:
            watch.update({"devices": [
                {"ip": A, "state": "online"},
                {"ip": B, "state": "known"},
            ]})
        probe.assert_called_once_with(A, 8123)
        status = watch.status()
        self.assertTrue(status["configured"])
        self.assertEqual([item["state"] for item in status["items"]], ["online", "unknown"])
        self.assertIsNone(status["items"][1]["checked_at"])

    def test_failure_is_scoped_to_tcp_service(self):
        watch = LocalServiceChecks((ServiceTarget("NAS", D, 5000),))
        with patch("app.service_checks.tcp_open", return_value=False):
            watch.update({"devices": [{"ip": D, "state": "recently_seen"}]})
        self.assertEqual(watch.status()["items"][0]["state"], "offline")
        with patch("app.service_checks.tcp_open") as probe:
            watch.update({"devices": []})
        probe.assert_not_called()
        self.assertEqual(watch.status()["items"][0]["state"], "unknown")


if __name__ == "__main__":
    unittest.main()
