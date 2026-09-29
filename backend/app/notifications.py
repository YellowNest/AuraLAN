"""Optional outbound webhook delivery for local AuraLAN events."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .brand import brand
from .persistence.device_store import DeviceStore

CHANNEL = "webhook"
DEFAULT_TIMEOUT_SECONDS = 5.0


def configured_webhook_url() -> str | None:
    raw = os.environ.get("AURALAN_WEBHOOK_URL", "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return raw


def configured_bearer_token() -> str | None:
    value = os.environ.get("AURALAN_WEBHOOK_BEARER_TOKEN", "").strip()
    return value or None


class WebhookNotifier:
    """Deliver persisted AuraLAN events in order without replaying old history."""

    def __init__(
        self,
        event_store: DeviceStore,
        *,
        url: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.event_store = event_store
        self.url = configured_webhook_url() if url is None else url
        self.bearer_token = configured_bearer_token() if bearer_token is None else bearer_token
        self.timeout_seconds = float(timeout_seconds)
        self.last_attempt_at: int | None = None
        self.last_success_at: int | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        if not self.url:
            return False
        parsed = urlparse(self.url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def status(self) -> dict[str, Any]:
        cursor = self.event_store.notification_cursor(CHANNEL) if self.enabled else None
        latest = self.event_store.latest_event_id() if self.enabled else 0
        return {
            "configured": self.enabled,
            "last_attempt_at": self.last_attempt_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "pending_events": max(0, latest - int(cursor or latest)),
        }

    def _post(self, payload: dict[str, Any]) -> None:
        if not self.enabled or not self.url:
            return
        metadata = brand()
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"AuraLAN/{metadata['version']}",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            if not 200 <= int(response.status) < 300:
                raise urllib.error.HTTPError(
                    self.url,
                    int(response.status),
                    "Webhook returned non-success status",
                    response.headers,
                    None,
                )

    @staticmethod
    def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "auralan.event",
            "source": "AuraLAN",
            "event": {
                "id": event["id"],
                "event_type": event["event_type"],
                "entity_id": event["entity_id"],
                "display_name": event.get("display_name"),
                "ip": event.get("ip"),
                "mac": event.get("mac"),
                "created_at": event["created_at"],
            },
        }

    def dispatch_pending(self, limit: int = 25) -> int:
        if not self.enabled:
            return 0

        cursor = self.event_store.notification_cursor(CHANNEL)
        if cursor is None:
            # Enabling notifications must not replay years of existing inventory
            # history. Prime at the current tail; only future events are delivered.
            self.event_store.set_notification_cursor(CHANNEL, self.event_store.latest_event_id())
            return 0

        delivered = 0
        for event in self.event_store.events_after(cursor, limit):
            self.last_attempt_at = int(time.time())
            try:
                self._post(self._event_payload(event))
            except urllib.error.HTTPError as exc:
                self.last_error = f"HTTP {exc.code}"
                break
            except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
                self.last_error = type(exc).__name__
                break

            self.event_store.set_notification_cursor(CHANNEL, int(event["id"]))
            cursor = int(event["id"])
            delivered += 1
            self.last_success_at = int(time.time())
            self.last_error = None

        return delivered

    def send_test(self) -> bool:
        if not self.enabled:
            return False
        self.last_attempt_at = int(time.time())
        try:
            self._post({
                "type": "auralan.test",
                "source": "AuraLAN",
                "created_at": int(time.time()),
                "message": "AuraLAN webhook test",
            })
        except urllib.error.HTTPError as exc:
            self.last_error = f"HTTP {exc.code}"
            return False
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            self.last_error = type(exc).__name__
            return False

        self.last_success_at = int(time.time())
        self.last_error = None
        return True
