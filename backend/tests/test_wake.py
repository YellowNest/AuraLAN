import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.main import meta, wake_device
from app.wake import (
    WakeConfig,
    magic_packet,
    normalize_mac,
    select_wake_mac,
    send_magic_packet,
    wake_config,
)


class WakeOnLanTests(unittest.TestCase):
    def test_wake_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            config = wake_config()
        self.assertFalse(config.enabled)
        self.assertEqual(config.broadcast, "255.255.255.255")
        self.assertEqual(config.port, 9)

    def test_wake_configuration_is_bounded_and_validated(self):
        with patch.dict(
            os.environ,
            {
                "AURALAN_ENABLE_WAKE_ON_LAN": "true",
                "AURALAN_WAKE_BROADCAST": "192.0.2.255",
                "AURALAN_WAKE_PORT": "7",
            },
            clear=True,
        ):
            config = wake_config()
        self.assertTrue(config.enabled)
        self.assertEqual(config.broadcast, "192.0.2.255")
        self.assertEqual(config.port, 7)

        with patch.dict(
            os.environ,
            {
                "AURALAN_ENABLE_WAKE_ON_LAN": "1",
                "AURALAN_WAKE_BROADCAST": "not-an-ip",
                "AURALAN_WAKE_PORT": "70000",
            },
            clear=True,
        ):
            fallback = wake_config()
        self.assertEqual(fallback.broadcast, "255.255.255.255")
        self.assertEqual(fallback.port, 9)

    def test_mac_validation_and_selection_prefer_global_unicast(self):
        self.assertEqual(normalize_mac("00-11-22-33-44-55"), "00:11:22:33:44:55")
        self.assertIsNone(normalize_mac("01:00:5e:00:00:01"))
        self.assertIsNone(normalize_mac("invalid"))

        device = {
            "mac_addresses": [
                "02:00:00:00:00:01",
                "00:11:22:33:44:55",
            ],
            "mac": "02:00:00:00:00:01",
        }
        self.assertEqual(select_wake_mac(device), "00:11:22:33:44:55")

    def test_magic_packet_has_standard_layout(self):
        packet = magic_packet("00:11:22:33:44:55")
        self.assertEqual(len(packet), 102)
        self.assertEqual(packet[:6], b"\xff" * 6)
        self.assertEqual(packet[6:12], bytes.fromhex("001122334455"))
        self.assertEqual(packet[-6:], bytes.fromhex("001122334455"))

    def test_send_magic_packet_uses_operator_configured_broadcast(self):
        config = WakeConfig(enabled=True, broadcast="192.0.2.255", port=9)
        sock = Mock()
        context = Mock()
        context.__enter__ = Mock(return_value=sock)
        context.__exit__ = Mock(return_value=False)

        with patch("app.wake.socket.socket", return_value=context):
            returned = send_magic_packet("00:11:22:33:44:55", config)

        self.assertEqual(returned, config)
        sock.setsockopt.assert_called_once()
        sock.settimeout.assert_called_once_with(2.0)
        packet, target = sock.sendto.call_args.args
        self.assertEqual(len(packet), 102)
        self.assertEqual(target, ("192.0.2.255", 9))

    def test_meta_only_advertises_wake_when_enabled(self):
        with patch("app.main.wake_config", return_value=WakeConfig(False, "255.255.255.255", 9)):
            self.assertFalse(meta()["capabilities"]["wake_on_lan"])
        with patch("app.main.wake_config", return_value=WakeConfig(True, "255.255.255.255", 9)):
            self.assertTrue(meta()["capabilities"]["wake_on_lan"])

    def test_wake_endpoint_is_opt_in_and_uses_known_device_mac(self):
        with patch("app.main.wake_config", return_value=WakeConfig(False, "255.255.255.255", 9)):
            with self.assertRaises(HTTPException) as raised:
                wake_device("sample")
        self.assertEqual(raised.exception.status_code, 403)

        config = WakeConfig(True, "192.0.2.255", 9)
        device = {
            "id": "sample",
            "mac": "00:11:22:33:44:55",
            "mac_addresses": ["00:11:22:33:44:55"],
        }
        with (
            patch("app.main.wake_config", return_value=config),
            patch("app.main.system_snapshot", return_value={"devices": [device]}),
            patch("app.main.send_magic_packet", return_value=config) as sender,
        ):
            result = wake_device("sample")

        sender.assert_called_once_with("00:11:22:33:44:55", config)
        self.assertTrue(result["sent"])
        self.assertEqual(result["device_id"], "sample")
        self.assertEqual(result["broadcast"], "192.0.2.255")


if __name__ == "__main__":
    unittest.main()
