from __future__ import annotations

import unittest
from unittest.mock import patch

from app.service_scan import scan_device_services, scan_ports, service_label


class ServiceScanTests(unittest.TestCase):
    def test_common_port_scan_returns_only_open_ports_sorted(self):
        with patch(
            "app.service_scan._check_port",
            side_effect=lambda _target, port, _timeout: port in {443, 22},
        ):
            self.assertEqual(scan_ports("192.0.2.40", [443, 80, 22]), [22, 443])

    def test_device_scan_uses_known_device_ipv4_only(self):
        device = {
            "id": "001122334455",
            "ip": "192.0.2.40",
            "ip_addresses": ["192.0.2.40"],
        }
        with (
            patch("app.service_scan.scan_ports", return_value=[22, 443]) as scanner,
            patch("app.service_scan.time.time", return_value=1234),
        ):
            result = scan_device_services(device)

        scanner.assert_called_once_with("192.0.2.40")
        self.assertEqual(result["device_id"], "001122334455")
        self.assertEqual(result["ip"], "192.0.2.40")
        self.assertEqual(result["open_ports"], [22, 443])
        self.assertEqual(result["checked_at"], 1234)

    def test_device_scan_rejects_device_without_usable_ipv4(self):
        with self.assertRaises(ValueError):
            scan_device_services({"id": "missing", "ip": "—", "ip_addresses": []})

    def test_service_labels_are_static_and_do_not_banner_grab(self):
        self.assertEqual(service_label(22), "SSH")
        self.assertEqual(service_label(8123), "Home Assistant")
        self.assertEqual(service_label(65535), "TCP")


if __name__ == "__main__":
    unittest.main()
