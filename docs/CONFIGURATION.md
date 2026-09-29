# Configuration

AuraLAN discovers the host dynamically and avoids machine-specific configuration where possible.

Production overrides can be placed in `/etc/default/auralan`. Development commands can export the same variables directly.

| Variable | Default | Purpose |
|---|---|---|
| `AURALAN_HOST` | `127.0.0.1` in supplied scripts/unit | HTTP bind address |
| `AURALAN_PORT` | `8787` | HTTP port |
| `AURALAN_DATA_DIR` | user state directory; `/var/lib/auralan` in supplied systemd unit | AuraLAN-owned SQLite/runtime state |
| `AURALAN_WIFI_INTERFACE` | automatic | Prefer one wireless interface when several exist |
| `AURALAN_PIHOLE_FTL_DB` | standard Pi-hole paths | Explicit path to a readable Pi-hole FTL database |
| `AURALAN_OUI_FILE` | standard Linux OUI paths | Explicit local/offline OUI registry |
| `AURALAN_MONITOR_INTERVAL` | `60` | Background discovery interval in seconds; `0` disables it, enabled values are bounded to 15–3600 seconds |
| `AURALAN_WEBHOOK_URL` | unset | Optional HTTP(S) endpoint for new-device and favorite-watch events |
| `AURALAN_WEBHOOK_BEARER_TOKEN` | unset | Optional bearer token sent only in the webhook Authorization header |
| `AURALAN_WEBHOOK_INCLUDE_IDENTIFIERS` | off | Opt in to include AuraLAN device ID, IP and MAC in webhook event payloads |
| `AURALAN_SERVICE` | `auralan` | Service name used by the local deployment helper |
| `AURALAN_HEALTH_URL` | `http://127.0.0.1:8787/api/v1/health` | Deployment/upgrade health-check URL |
| `AURALAN_URL` | `http://127.0.0.1:8787` | Browser sanity-test target |

## Wi-Fi interface selection

Normally no override is required. AuraLAN examines all active NetworkManager Wi-Fi connections and all interfaces reported by `iw`, then confirms AP mode with `iw`.

If a host has unusual wireless topology:

```bash
AURALAN_WIFI_INTERFACE=hotspot0
```

The name is an override, not a built-in assumption.

## Continuous monitoring

AuraLAN keeps discovering the local network even when no browser is open. By default one background discovery pass runs every 60 seconds, which keeps first/last-seen timestamps, remembered devices, activity history and favorite-device watch state useful without depending on dashboard polling.

To change the interval:

```bash
AURALAN_MONITOR_INTERVAL=120
```

Set it to `0` to disable background discovery. Positive values below 15 seconds are clamped to 15 seconds to avoid accidental high-frequency scanning.

The monitor uses the same bounded discovery code and local cache/store as normal dashboard refreshes. It does not enable telemetry or send device information anywhere.

## Webhook notifications

AuraLAN can deliver persisted local events to one operator-configured HTTP(S) webhook. This works well with Home Assistant webhook automations, local automation servers, or another endpoint you control.

For example:

```bash
AURALAN_WEBHOOK_URL=http://homeassistant.local:8123/api/webhook/YOUR_WEBHOOK_ID
```

Supported event types currently include:

- `device_first_seen`
- `favorite_not_seen`
- `favorite_seen_again`

When a webhook is enabled for the first time, AuraLAN starts at the current end of its event history instead of replaying old discoveries. New events are delivered in order. A failed event remains pending and is retried on a later monitor pass.

By default webhook event payloads do **not** include IP addresses, MAC addresses or AuraLAN's internal device identifier. To opt in:

```bash
AURALAN_WEBHOOK_INCLUDE_IDENTIFIERS=1
```

If the receiver expects a bearer token:

```bash
AURALAN_WEBHOOK_BEARER_TOKEN=replace-me
```

The configured URL and bearer token are never returned by AuraLAN's status, diagnostics, or Prometheus endpoints. The Settings page can send an explicit test event once a webhook is configured.

## Pi-hole FTL

AuraLAN checks standard local Pi-hole database locations. For a custom installation:

```bash
AURALAN_PIHOLE_FTL_DB=/path/to/pihole-FTL.db
```

The file is opened read-only.

## Local data

AuraLAN stores only its own metadata, such as user aliases, identity cache data, and observation timestamps, in its SQLite database.

Runtime state is deliberately separate from the source checkout:

- the supplied systemd service uses `/var/lib/auralan/auralan.db`
- an ordinary user process defaults to `$XDG_STATE_HOME/auralan/auralan.db`, or `~/.local/state/auralan/auralan.db` when `XDG_STATE_HOME` is unset
- `AURALAN_DATA_DIR` can override either location

For example:

```bash
AURALAN_DATA_DIR=/srv/auralan
```

Host-specific settings belong in `/etc/default/auralan` for the supplied systemd service, or in the process environment for development. They are not stored in the Git checkout.

Do not place credentials in the repository. Environment overrides containing private paths or deployment-specific values belong on the host.

## Prometheus

AuraLAN exposes aggregate metrics at `/metrics` on the same HTTP listener as the dashboard. No extra dependency or token is required.

Example Prometheus scrape configuration:

```yaml
scrape_configs:
  - job_name: auralan
    static_configs:
      - targets: ['127.0.0.1:8787']
```

The endpoint intentionally excludes device names, IDs, IP/MAC addresses, notes, and per-device labels. If AuraLAN is exposed beyond loopback, protect `/metrics` with the same reverse-proxy/access policy as the dashboard.

## Offline OUI registry

AuraLAN never requires an online MAC-vendor service. It reads common Linux OUI database locations automatically.

For a custom local registry:

```bash
AURALAN_OUI_FILE=/path/to/oui.txt
```

Unknown prefixes remain unknown rather than triggering a cloud lookup.
