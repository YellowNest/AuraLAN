from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.main import meta, probe_device_reachability
from app.probe import ProbeUnavailable, probe_device, select_probe_ip


class DeviceProbeTests(unittest.TestCase):
    def test_select_probe_ip_prefers_first_usable_ipv4(self):
        device = {
            "ip_addresses": ["—", "127.0.0.1", "ff02::1", "192.168.1.44"],
            "ip": "192.168.1.55",
        }
        self.assertEqual(select_probe_ip(device), "192.168.1.44")

    def test_probe_reports_reply_and_latency(self):
        completed = subprocess.CompletedProcess(
            args=["ping"],
            returncode=0,
            stdout="64 bytes from 192.168.1.44: icmp_seq=1 ttl=64 time=4.21 ms\n",
            stderr="",
        )
        device = {"id": "sample", "ip_addresses": ["192.168.1.44"], "ip": "192.168.1.44"}

        with (
            patch("app.probe.shutil.which", return_value="/usr/bin/ping"),
            patch("app.probe.subprocess.run", return_value=completed) as runner,
            patch("app.probe.time.time", return_value=1234567890.9),
        ):
            result = probe_device(device)

        self.assertTrue(result["reply_received"])
        self.assertEqual(result["latency_ms"], 4.21)
        self.assertEqual(result["checked_at"], 1234567890)
        runner.assert_called_once_with(
            ["/usr/bin/ping", "-n", "-c", "1", "-W", "1", "192.168.1.44"],
            capture_output=True,
            text=True,
            timeout=2.5,
            check=False,
        )

    def test_probe_treats_no_reply_as_observation_not_error(self):
        completed = subprocess.CompletedProcess(
            args=["ping"],
            returncode=1,
            stdout="1 packets transmitted, 0 received, 100% packet loss\n",
            stderr="",
        )
        with (
            patch("app.probe.shutil.which", return_value="/usr/bin/ping"),
            patch("app.probe.subprocess.run", return_value=completed),
        ):
            result = probe_device({"id": "quiet", "ip": "10.0.0.8", "ip_addresses": []})

        self.assertFalse(result["reply_received"])
        self.assertIsNone(result["latency_ms"])

    def test_probe_requires_ping_and_usable_ipv4(self):
        with patch("app.probe.shutil.which", return_value=None):
            with self.assertRaises(ProbeUnavailable):
                probe_device({"id": "sample", "ip": "192.168.1.44"})

        with patch("app.probe.shutil.which", return_value="/usr/bin/ping"):
            with self.assertRaises(ValueError):
                probe_device({"id": "sample", "ip_addresses": ["::1", "127.0.0.1"], "ip": "—"})

    def test_meta_advertises_probe_only_when_available(self):
        with patch("app.main.probe_available", return_value=False):
            self.assertFalse(meta()["capabilities"]["device_probe"])
        with patch("app.main.probe_available", return_value=True):
            self.assertTrue(meta()["capabilities"]["device_probe"])

    def test_probe_endpoint_only_targets_a_known_device(self):
        result = {
            "device_id": "sample",
            "ip": "192.168.1.44",
            "reply_received": True,
            "latency_ms": 1.2,
            "checked_at": 123,
        }
        device = {"id": "sample", "ip": "192.168.1.44", "ip_addresses": ["192.168.1.44"]}

        with (
            patch("app.main.system_snapshot", return_value={"devices": [device]}),
            patch("app.main.run_device_probe", return_value=result) as runner,
        ):
            self.assertEqual(probe_device_reachability("sample"), result)
        runner.assert_called_once_with(device)

        with patch("app.main.system_snapshot", return_value={"devices": []}):
            with self.assertRaises(HTTPException) as raised:
                probe_device_reachability("missing")
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
