import unittest
from unittest.mock import patch

from app.service_checks import LocalServiceChecks, ServiceTarget, configured_targets


class ServiceChecksTests(unittest.TestCase):
    def test_configuration_is_bounded_and_private(self):
        parsed = configured_targets('[{"name":"Home Assistant","ip":"192.168.1.50","port":8123},'
                                    '{"name":"duplicate","ip":"192.168.1.50","port":8123},'
                                    '{"name":"outside","ip":"203.0.113.50","port":443},'
                                    '{"name":"router","ip":"10.0.0.1","port":443},'
                                    '{"name":"bad","ip":"127.0.0.1","port":80}]')
        self.assertEqual([(x.name, x.ip, x.port) for x in parsed], [
            ("Home Assistant", "192.168.1.50", 8123),
            ("router", "10.0.0.1", 443),
        ])
        self.assertEqual(configured_targets("{}"), ())
        self.assertEqual(configured_targets("[{}]"), ())
        self.assertEqual(configured_targets("x" * 4097), ())
        self.assertEqual(configured_targets("[]"), ())

    def test_checks_only_probe_observed_private_targets(self):
        watch = LocalServiceChecks((ServiceTarget("HA", "192.168.1.50", 8123),
                                    ServiceTarget("NAS", "192.168.1.10", 443)))
        with patch("app.service_checks.tcp_open", return_value=True) as probe:
            watch.update({"devices": [
                {"ip": "192.168.1.50", "state": "online"},
                {"ip": "192.168.1.10", "state": "known"},
            ]})
        probe.assert_called_once_with("192.168.1.50", 8123)
        status = watch.status()
        self.assertTrue(status["configured"])
        self.assertEqual([item["state"] for item in status["items"]], ["online", "unknown"])
        self.assertIsNone(status["items"][1]["checked_at"])

    def test_failure_is_scoped_to_tcp_service(self):
        watch = LocalServiceChecks((ServiceTarget("NAS", "172.16.5.10", 5000),))
        with patch("app.service_checks.tcp_open", return_value=False):
            watch.update({"devices": [{"ip": "172.16.5.10", "state": "recently_seen"}]})
        self.assertEqual(watch.status()["items"][0]["state"], "offline")
        with patch("app.service_checks.tcp_open") as probe:
            watch.update({"devices": []})
        probe.assert_not_called()
        self.assertEqual(watch.status()["items"][0]["state"], "unknown")


if __name__ == "__main__":
    unittest.main()
