# Home Assistant

AuraLAN can integrate with Home Assistant without adding a cloud account, MQTT dependency, or Home Assistant-specific runtime dependency.

There are two complementary paths:

1. poll AuraLAN's aggregate Home Assistant summary for local sensors;
2. configure AuraLAN's reliable webhook delivery for event-driven automations.

Both remain opt-in and local to the operator's network.

## Aggregate REST summary

AuraLAN exposes:

```text
GET /api/v1/integrations/home-assistant
```

The response is intentionally aggregate-only. It includes counts and runtime health, but no device names, AuraLAN device IDs, IP addresses, MAC addresses, notes, locations, or tags.

Example payload:

```json
{
  "version": "0.6.0-dev",
  "api_version": "v1",
  "generated_at": "2026-09-29T19:00:00+02:00",
  "system_state": "healthy",
  "attention_count": 0,
  "devices_total": 18,
  "devices_online": 9,
  "devices_not_seen_now": 3,
  "favorites_total": 2,
  "favorites_not_seen_now": 0,
  "new_devices_24h": 1,
  "services_detected": 4,
  "services_online": 4,
  "discovery_errors": 0,
  "monitor_running": true,
  "monitor_last_success_at": 1790701200,
  "webhook_configured": true,
  "webhook_pending_events": 0,
  "wake_on_lan_enabled": false
}
```

This endpoint is suitable for Home Assistant REST sensors. Replace the example host with the address Home Assistant uses to reach AuraLAN:

```yaml
rest:
  - resource: http://auralan.example:8787/api/v1/integrations/home-assistant
    scan_interval: 60
    sensor:
      - name: AuraLAN Devices
        unique_id: auralan_devices_total
        value_template: "{{ value_json.devices_total }}"
        unit_of_measurement: "devices"

      - name: AuraLAN Devices Online
        unique_id: auralan_devices_online
        value_template: "{{ value_json.devices_online }}"
        unit_of_measurement: "devices"

      - name: AuraLAN Favorites Not Seen
        unique_id: auralan_favorites_not_seen
        value_template: "{{ value_json.favorites_not_seen_now }}"
        unit_of_measurement: "devices"

      - name: AuraLAN Discovery Errors
        unique_id: auralan_discovery_errors
        value_template: "{{ value_json.discovery_errors }}"

      - name: AuraLAN Webhook Pending
        unique_id: auralan_webhook_pending
        value_template: "{{ value_json.webhook_pending_events }}"
```

The exact Home Assistant configuration layout can vary by installation and release. The important contract is AuraLAN's JSON endpoint; keep Home Assistant-specific configuration in Home Assistant rather than in the AuraLAN checkout.

## Event-driven webhook automation

AuraLAN can also POST persisted events to a Home Assistant webhook. Configure the webhook URL in AuraLAN's service environment:

```bash
AURALAN_WEBHOOK_URL=http://homeassistant.local:8123/api/webhook/YOUR_WEBHOOK_ID
```

The existing webhook channel delivers:

- `device_first_seen`
- `favorite_not_seen`
- `favorite_seen_again`

A typical Home Assistant automation can trigger on that webhook and inspect `trigger.json.event.event_type` and `trigger.json.event.display_name`.

By default AuraLAN deliberately omits device ID, IP, and MAC from webhook payloads. Enable identifiers only when an automation genuinely requires them:

```bash
AURALAN_WEBHOOK_INCLUDE_IDENTIFIERS=1
```

See [Configuration](CONFIGURATION.md) for delivery retries, bearer-token support, privacy behavior, and the favorite-watch debounce.

## Presence history

Per-device presence history stays local in AuraLAN and is not automatically sent to Home Assistant. This is deliberate: a full presence timeline can be both noisy and more privacy-sensitive than aggregate health or explicitly selected favorite-watch events.

Applications that need the timeline can read it locally from:

```text
GET /api/v1/devices/{id}/presence?limit=50
```

## Wake-on-LAN

When AuraLAN's Wake-on-LAN feature is explicitly enabled, an automation can call the local AuraLAN endpoint for a known device:

```text
POST /api/v1/devices/{id}/wake
```

AuraLAN still validates the device and MAC server-side. Wake-on-LAN is disabled by default; see [Configuration](CONFIGURATION.md).

## Network exposure

AuraLAN's API has the same trust boundary as its dashboard. If Home Assistant is on another host, expose AuraLAN only to the network segment that needs it and use the same reverse-proxy/access-control policy you use for the dashboard.

The Home Assistant summary endpoint does not contain per-device identity data, but other AuraLAN endpoints do.
