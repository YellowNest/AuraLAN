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
| `AURALAN_PIHOLE_DIR` | `/etc/pihole` | Alternate Pi-hole directory for local custom-name files and host-service detection in container deployments |
| `AURALAN_OUI_FILE` | standard Linux OUI paths | Explicit local/offline OUI registry |
| `AURALAN_DOCKER_SOCKET` | unset | Explicit local Docker Engine UNIX socket for bounded read-only service discovery |
| `AURALAN_HOST_PROC` | `/proc` | Alternate host procfs root, primarily for the container deployment |
| `AURALAN_HOST_SYS` | `/sys` | Alternate host sysfs root, primarily for the container deployment |
| `AURALAN_HOSTNAME_FILE` | unset | Alternate read-only hostname file used by container deployments |
| `AURALAN_HOSTS_FILE` | `/etc/hosts` | Alternate read-only hosts file used for local-name enrichment |
| `AURALAN_HOST_ROOT` | `/` natively; unset in container mode | Filesystem path used only for host storage usage |
| `AURALAN_MONITOR_INTERVAL` | `60` | Background discovery interval in seconds; `0` disables it, enabled values are bounded to 15–3600 seconds |
| `AURALAN_WATCH_MISSING_GRACE` | `120` | Seconds a favorite must remain unobserved before AuraLAN emits `favorite_not_seen`; bounded to 0–86400 |
| `AURALAN_PRESENCE_MISSING_GRACE` | `180` | Seconds a device must remain unobserved before AuraLAN records a general presence-history absence; bounded to 0–86400 |
| `AURALAN_WEBHOOK_URL` | unset | Optional HTTP(S) endpoint for new-device and favorite-watch events |
| `AURALAN_WEBHOOK_BEARER_TOKEN` | unset | Optional bearer token sent only in the webhook Authorization header |
| `AURALAN_WEBHOOK_INCLUDE_IDENTIFIERS` | off | Opt in to include AuraLAN device ID, IP and MAC in webhook event payloads |
| `AURALAN_ENABLE_WAKE_ON_LAN` | off | Explicitly enable the Wake-on-LAN action for known devices |
| `AURALAN_WAKE_BROADCAST` | `255.255.255.255` | IPv4 broadcast address used for Wake-on-LAN magic packets |
| `AURALAN_WAKE_PORT` | `9` | UDP destination port for Wake-on-LAN packets |
| `AURALAN_SERVICE` | `auralan` | Service name used by the local deployment helper |
| `AURALAN_HEALTH_URL` | `http://127.0.0.1:8787/api/v1/health` | Deployment/upgrade health-check URL |
| `AURALAN_URL` | `http://127.0.0.1:8787` | Browser sanity-test target |

## Container-specific host views

The official container keeps host access explicit. Its Compose file sets `AURALAN_HOST_PROC`, `AURALAN_HOST_SYS`, `AURALAN_HOSTNAME_FILE` and `AURALAN_HOSTS_FILE` to read-only bind mounts so host identity and metrics are not confused with the container itself.

`AURALAN_CONTAINER_MODE=1` is set by the official image. In that mode AuraLAN deliberately leaves host storage usage unavailable unless `AURALAN_HOST_ROOT` is explicitly configured; reporting the container overlay filesystem as the host disk would be misleading.

`AURALAN_DOCKER_SOCKET` is opt-in. When configured, AuraLAN uses a small bounded set of Docker Engine GET requests and only retains presentation fields needed for service visibility. Docker socket access is still highly privileged at the host level and should only be granted deliberately.

See **[Docker](DOCKER.md)** for the supported Compose deployment, capability choices, optional D-Bus access and Docker-socket overlay.

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

## Device presence history

AuraLAN can keep a compact local transition history for each remembered device. The history records only meaningful state changes: when a device has remained unobserved long enough to be considered **not seen**, and when AuraLAN later sees it again.

The default absence grace period is 180 seconds:

```bash
AURALAN_PRESENCE_MISSING_GRACE=180
```

A short discovery gap is therefore ignored instead of becoming a misleading timeline event. Positive evidence cancels a pending absence immediately. Set the value to `0` only when immediate transition logging is explicitly wanted.

Presence history is bounded locally to avoid unbounded database growth. AuraLAN keeps at most 200 transitions per device and 5000 transitions overall. These events stay in AuraLAN's SQLite state and are not sent through the webhook notifier.

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

A single missed discovery pass is weak evidence. By default a favorite must remain unobserved for 120 seconds before AuraLAN persists and delivers `favorite_not_seen`. A positive observation cancels a pending absence immediately, while `favorite_seen_again` is emitted immediately after a confirmed absence when the device returns. Set `AURALAN_WATCH_MISSING_GRACE=0` only if immediate absence events are explicitly wanted.

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

## Wake-on-LAN

Wake-on-LAN is disabled by default because it is an active network action rather than passive discovery.

Enable it explicitly in the service environment:

```bash
AURALAN_ENABLE_WAKE_ON_LAN=1
```

When enabled, AuraLAN exposes a **Wake device** action for remembered devices with a usable unicast MAC address. The action sends one standard WOL magic packet and does not change DHCP, DNS, firewall, switch, router, BIOS, or operating-system settings.

The default packet destination is the limited IPv4 broadcast address on UDP port 9. Networks that require a directed broadcast or another WOL port can override them:

```bash
AURALAN_WAKE_BROADCAST=192.0.2.255
AURALAN_WAKE_PORT=9
```

The target device still needs Wake-on-LAN enabled in its firmware/NIC/operating-system configuration. AuraLAN cannot guarantee that a device will wake merely because the packet was sent.

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
