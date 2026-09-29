import os
import sqlite3
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.notifications import WebhookNotifier, configured_webhook_url
from app.persistence.device_store import DeviceStore


def add_first_seen(device_store: DeviceStore, device_id: str, ip: str) -> int:
    metadata = device_store.enrich([device_id])[device_id]
    formatted = ":".join(device_id[index:index + 2] for index in range(0, 12, 2)).upper()
    device_store.record_first_seen(
        [{
            "id": device_id,
            "display_name": f"Device {device_id[-2:]}",
            "ip": ip,
            "mac": formatted,
            "mac_addresses": [formatted],
            "first_seen_at": metadata["first_seen_at"],
        }],
        {device_id},
    )
    return device_store.latest_event_id()


class WebhookNotificationTests(unittest.TestCase):
    def test_invalid_webhook_scheme_is_not_enabled(self):
        with patch.dict(os.environ, {"AURALAN_WEBHOOK_URL": "file:///tmp/hook"}, clear=False):
            self.assertIsNone(configured_webhook_url())

    def test_existing_history_is_primed_and_not_replayed(self):
        with TemporaryDirectory() as temp_dir:
            event_store = DeviceStore(Path(temp_dir))
            first_id = add_first_seen(event_store, "001122334455", "192.0.2.10")
            notifier = WebhookNotifier(event_store, url="http://example.invalid/hook")

            with patch.object(notifier, "_post") as post:
                self.assertEqual(notifier.dispatch_pending(), 0)
                post.assert_not_called()

            self.assertEqual(event_store.notification_cursor("webhook"), first_id)

            second_id = add_first_seen(event_store, "001122334466", "192.0.2.11")
            with patch.object(notifier, "_post") as post:
                self.assertEqual(notifier.dispatch_pending(), 1)
                post.assert_called_once()

            self.assertEqual(event_store.notification_cursor("webhook"), second_id)
            self.assertEqual(notifier.status()["pending_events"], 0)

    def test_failed_delivery_stays_pending_for_retry(self):
        with TemporaryDirectory() as temp_dir:
            event_store = DeviceStore(Path(temp_dir))
            initial = add_first_seen(event_store, "001122334455", "192.0.2.10")
            event_store.set_notification_cursor("webhook", initial)
            next_id = add_first_seen(event_store, "001122334466", "192.0.2.11")

            notifier = WebhookNotifier(event_store, url="http://example.invalid/hook")
            with patch.object(notifier, "_post", side_effect=urllib.error.URLError("offline")):
                self.assertEqual(notifier.dispatch_pending(), 0)

            self.assertEqual(event_store.notification_cursor("webhook"), initial)
            self.assertEqual(notifier.status()["pending_events"], 1)
            self.assertEqual(notifier.status()["last_error"], "URLError")

    def test_pending_count_ignores_deleted_event_id_gaps(self):
        with TemporaryDirectory() as temp_dir:
            event_store = DeviceStore(Path(temp_dir))
            first_id = add_first_seen(event_store, "001122334455", "192.0.2.10")
            second_id = add_first_seen(event_store, "001122334466", "192.0.2.11")
            third_id = add_first_seen(event_store, "001122334477", "192.0.2.12")
            event_store.set_notification_cursor("webhook", first_id)

            with sqlite3.connect(event_store.path) as connection:
                connection.execute("DELETE FROM device_events WHERE id = ?", (second_id,))
                connection.commit()

            self.assertGreater(third_id - first_id, 1)

            notifier = WebhookNotifier(event_store, url="http://example.invalid/hook")
            self.assertEqual(notifier.status()["pending_events"], 1)

            with patch.object(notifier, "_post") as post:
                self.assertEqual(notifier.dispatch_pending(), 1)
                post.assert_called_once()

            self.assertEqual(event_store.notification_cursor("webhook"), third_id)
            self.assertEqual(notifier.status()["pending_events"], 0)

    def test_default_payload_omits_network_identifiers(self):
        with TemporaryDirectory() as temp_dir:
            notifier = WebhookNotifier(
                DeviceStore(Path(temp_dir)),
                url="http://example.invalid/hook",
                include_identifiers=False,
            )
            payload = notifier._event_payload({
                "id": 7,
                "event_type": "device_first_seen",
                "entity_id": "001122334455",
                "display_name": "Phone",
                "ip": "192.0.2.12",
                "mac": "00:11:22:33:44:55",
                "created_at": 123,
            })

            event = payload["event"]
            self.assertEqual(event["event_type"], "device_first_seen")
            self.assertEqual(event["display_name"], "Phone")
            self.assertNotIn("entity_id", event)
            self.assertNotIn("ip", event)
            self.assertNotIn("mac", event)

    def test_identifier_opt_in_adds_device_identity_fields(self):
        with TemporaryDirectory() as temp_dir:
            notifier = WebhookNotifier(
                DeviceStore(Path(temp_dir)),
                url="http://example.invalid/hook",
                include_identifiers=True,
            )
            payload = notifier._event_payload({
                "id": 7,
                "event_type": "favorite_not_seen",
                "entity_id": "001122334455",
                "display_name": "Camera",
                "ip": "192.0.2.12",
                "mac": "00:11:22:33:44:55",
                "created_at": 123,
            })

            self.assertEqual(payload["event"]["entity_id"], "001122334455")
            self.assertEqual(payload["event"]["ip"], "192.0.2.12")
            self.assertEqual(payload["event"]["mac"], "00:11:22:33:44:55")

    def test_status_never_exposes_webhook_url_or_bearer_token(self):
        with TemporaryDirectory() as temp_dir:
            notifier = WebhookNotifier(
                DeviceStore(Path(temp_dir)),
                url="https://example.invalid/secret-path",
                bearer_token="top-secret",
            )
            status = notifier.status()

            self.assertTrue(status["configured"])
            self.assertNotIn("url", status)
            self.assertNotIn("bearer_token", status)
            self.assertNotIn("top-secret", repr(status))
            self.assertNotIn("secret-path", repr(status))

    def test_send_test_uses_configured_delivery_path(self):
        with TemporaryDirectory() as temp_dir:
            notifier = WebhookNotifier(
                DeviceStore(Path(temp_dir)),
                url="http://example.invalid/hook",
            )
            with patch.object(notifier, "_post") as post:
                self.assertTrue(notifier.send_test())
                post.assert_called_once()

            self.assertIsNotNone(notifier.status()["last_success_at"])
            self.assertIsNone(notifier.status()["last_error"])


if __name__ == "__main__":
    unittest.main()
