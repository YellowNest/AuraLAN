<p align="center">
  <img src="frontend/assets/icons/logo-mark.svg" width="128" height="128" alt="AuraLAN logo">
</p>

<h1 align="center">AuraLAN</h1>

<p align="center">
  <strong>Your network, clearly.</strong><br>
  A self-hosted, local-first LAN inventory and network monitoring console for Linux and Raspberry Pi.
</p>

<p align="center">
  <a href="https://github.com/YellowNest/AuraLAN/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/YellowNest/AuraLAN/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB">
  <img alt="Release 1.0.0" src="https://img.shields.io/badge/release-1.0.0-2563EB">
  <img alt="Local first" src="https://img.shields.io/badge/data-local--first-22C55E">
  <img alt="No telemetry" src="https://img.shields.io/badge/telemetry-none-64748B">
</p>

AuraLAN turns the network state already available on a Linux host into a focused dashboard for people who want to understand their LAN without living in terminals.

It answers the useful questions first: **what is connected, what each device probably is, whether it is online, how it was discovered, and which local services need attention.**

## Why AuraLAN

| | |
|---|---|
| **Human-readable devices** | Combines DHCP, neighbours, Wi-Fi station data, local names and service discovery into conservative device identities. |
| **Identity Intelligence** | Shows how much local evidence supports each identity, highlights devices that still need attention, and improves recognition through HomeKit, Matter, UPnP/DNS-SD and offline Linux OUI data without cloud fingerprinting. |
| **Network Baseline** | Capture the devices you expect to see and let AuraLAN highlight what appeared or disappeared since that reference point, entirely locally and without pretending a change is automatically a threat. |
| **Activity Center** | A first-class local timeline brings new devices, favorite watch changes, Service Exposure diffs and baseline actions together so you can see what changed without turning observations into security verdicts. |
| **One-click reachability check** | From any known device, send one local ICMP echo and see whether a reply came back plus round-trip latency when available. No cloud service and no continuous ping loop. |
| **Service Exposure snapshots** | On demand, check a small fixed set of common TCP ports on a known device, save the result locally, and see what opened or closed since the previous check. No subnet scan, banner grabbing or cloud fingerprinting. |
| **A device inventory that remembers** | Track first/last seen time and a debounced per-device presence timeline, add aliases, locations and tags, keep private notes, mark important devices, filter and sort the inventory, forget stale remembered devices safely, and export it as CSV or JSON. |
| **Runs even when the dashboard is closed** | Continuous local discovery refreshes the inventory and history in the background instead of depending on an open browser tab. |
| **Home Assistant & webhook friendly** | An aggregate REST summary feeds local Home Assistant sensors without device identity data, while optional reliable webhooks report new devices and favorite watch-state changes. |
| **Safe opt-in actions** | Wake-on-LAN can be enabled explicitly to wake known devices without turning AuraLAN into a router or remote shell. |
| **Local by design** | No account, telemetry, cloud lookup, remote fonts, CDN scripts or third-party MAC/vendor API. |
| **Useful technical depth** | Friendly names first; IP, MAC, interfaces, leases and identity evidence remain available when needed. |
| **Evidence-based network map** | Current devices are grouped by confirmed Wi-Fi, Ethernet, VPN or other connection evidence without inventing switch-level topology. |
| **One place for local infrastructure** | Network state plus optional Docker, Pi-hole, WireGuard/wg-easy and Caddy visibility. |
| **Prometheus-ready** | A dependency-free `/metrics` endpoint exposes aggregate device, service and host health without device names, IP addresses, MAC addresses or notes. |
| **Works with imperfect systems** | Optional providers fail independently instead of taking down the dashboard. |
| **Phone to desktop** | Responsive interface with light, dark and system appearance. |

## What AuraLAN discovers

AuraLAN can combine local evidence from:

- Linux neighbour and route tables
- NetworkManager when present
- any wireless interface reported by `iw`, without assuming a conventional interface name
- access-point station signal data
- dnsmasq leases
- local host files and the host resolver
- Avahi/mDNS and DNS-SD
- NetBIOS names
- SSDP/UPnP device descriptions from already-known LAN clients
- Pi-hole FTL history when readable
- local/offline OUI registries installed on the host, including systemd/udev hwdb when available
- standards-based HomeKit category and Matter service hints

Device identity is deliberately conservative. An OUI can identify an organization; it cannot prove an exact model. AuraLAN keeps the raw evidence separate from the friendly presentation. The Devices view also summarizes identity coverage and the evidence sources behind each device so a user can immediately see which identities are well supported and which still need a useful local name.

### Device inventory

AuraLAN remembers when a device was first and last observed. You can give devices your own names, assign a location such as a room or rack, add lightweight tags, keep a short local note and mark important devices as favorites. Favorites also act as a lightweight local watchlist: if a favorite is only present in remembered inventory and has no current observation, AuraLAN surfaces that on Overview without claiming the device is definitely offline. The device view can surface favorites, newly seen devices, connection type and devices that still need a better identity.

Once AuraLAN has observed a device, it also keeps a compact last-known presentation in local state. If the device later disappears from the current discovery pass it remains searchable as **Not seen now**, with its last-seen time and last-known identity instead of silently vanishing from the inventory. Remembered devices that are no longer observed can be explicitly forgotten; AuraLAN removes its own saved identity, metadata, activity, watch state and presence history, and the device will be treated as new if it is discovered again later.

A local **Network Baseline** can capture the devices AuraLAN currently observes. Later, the Overview and Devices filters show what is new since that baseline and which baseline devices are not currently seen. Multi-interface devices are matched across their known MAC identities so an adapter-order change does not create a false new device. The baseline is local state and can be replaced or removed without deleting inventory history.

When the host provides the standard `ping` utility, each device inspector also gets an on-demand **Check reachability** action. AuraLAN sends exactly one ICMP echo to a known IPv4 address and reports the reply and round-trip latency when available. The result is intentionally phrased as a ping observation: a device can be online while refusing ICMP.

The device inspector also provides an on-demand **Service Exposure** check. It attempts TCP connections to a small built-in list of common service ports only on that already-known device, never scans an address range, and does not read banners or application data. AuraLAN stores a bounded local history of these snapshots and highlights ports that newly accepted connections or stopped accepting them since the previous check. A port label is a conventional hint based on the port number, not proof of which application is running there.

AuraLAN also keeps a bounded per-device presence timeline. A device must remain unobserved for a grace period before AuraLAN records **Not seen**, so one weak discovery miss does not become false history. When positive evidence returns, AuraLAN records **Seen again**. These are observation transitions, not claims about whether a device was powered off or physically present.

The **Activity Center** turns those local observations into one readable change timeline. It combines devices first seen by AuraLAN, confirmed favorite-watch transitions, Service Exposure differences and operator baseline actions. Each event keeps only the evidence AuraLAN actually has; a changed port or missing observation is reported as a change, not promoted into an intrusion or threat claim.

All of that inventory data stays in AuraLAN's local SQLite state. AuraLAN also keeps a compact first-seen discovery history, so the Overview can answer "what showed up recently?" without sending device data anywhere. Existing installations backfill this history from their already stored first-seen timestamps, so upgrading does not start with an empty timeline.

A background monitor performs local discovery every 60 seconds by default, so first/last-seen data, recent discoveries and the favorite-device watchlist continue updating when the web interface is closed. The interval is configurable or can be disabled entirely.

Home Assistant can poll AuraLAN's aggregate integration summary for device/service counts and monitor health without receiving device names, IDs, IP/MAC addresses, notes, locations or tags. If an operator also configures a webhook, AuraLAN can deliver newly persisted device events to Home Assistant or another HTTP(S) receiver. Delivery is ordered and retryable, old history is not replayed when notifications are first enabled, and IP/MAC/internal device IDs are omitted unless explicitly enabled. Favorite-absence events are debounced by default so one transient discovery miss does not create a false alert.

A "new" device means **new to this AuraLAN installation within the last 24 hours**; it is an observation aid, not an intrusion verdict. Recent-discovery entries are likewise local observations, not security alerts.

The Devices view can search locations and tags, sort by smart order, name, last seen, first seen, location or IP address, and export the current inventory as CSV or JSON directly in the browser. Exports can contain private IP/MAC addresses and user notes, so AuraLAN labels that clearly before download. CSV cells that begin like spreadsheet formulas are neutralized before export because network-provided device names are not trusted input.

## What AuraLAN does not do

AuraLAN is not a router, firewall, DHCP server, DNS server, Wi-Fi controller, VPN server or Docker manager.

By default AuraLAN does **not** change host networking, firewall rules, DHCP, DNS, Docker, Caddy, Pi-hole or WireGuard. Writes are limited to AuraLAN's own local state: observed device identity/presence, local activity and scan history, the operator-defined network baseline, and user-owned metadata such as aliases, notes, locations, tags and favorites.

AuraLAN also includes an explicitly enabled Wake-on-LAN action. It sends one standard local magic packet to a known MAC address; it does not execute commands on the target or modify network/system configuration. The reachability action sends one on-demand ICMP echo only. Service Exposure is likewise explicit and per-device: AuraLAN does not continuously scan ports, sweep subnets, read service banners, or probe arbitrary addresses.

## Quick start

For development or evaluation:

```bash
git clone https://github.com/YellowNest/AuraLAN.git
cd AuraLAN
./scripts/dev.sh
```

By default the development server binds to `127.0.0.1:8787`.

To test from another device on your LAN:

```bash
AURALAN_HOST=0.0.0.0 ./scripts/dev.sh
```

Then open `http://HOST-IP:8787`.

For a system service, a clean installer, permissions, reverse proxy setup and production layout, read **[Installation](docs/INSTALLATION.md)**.

## Configuration

AuraLAN prefers runtime discovery over machine-specific configuration. Optional overrides are environment variables rather than a host-specific config file.

See **[Configuration](docs/CONFIGURATION.md)** for:

- preferred Wi-Fi/AP interface
- bind address and port
- data directory
- non-standard Pi-hole FTL database location
- continuous background monitoring interval
- per-device presence-history absence grace period
- Home Assistant REST summary, webhook notifications and privacy controls
- opt-in Wake-on-LAN action and broadcast settings
- service/deployment overrides

For ready-to-adapt REST sensor and webhook examples, see **[Home Assistant](docs/HOME_ASSISTANT.md)**.

## Compatibility

AuraLAN is designed for modern Linux and is tested primarily on Debian-family systems and Raspberry Pi. NetworkManager is optional: AP detection can fall back to interfaces reported directly by `iw`.

See **[Compatibility](docs/COMPATIBILITY.md)** for provider requirements and graceful-degradation behavior.

## Architecture

```text
browser (native ES modules)
        │  same-origin /api/v1
        ▼
FastAPI local API
        │
        ├── host/network: iproute · iw · NetworkManager · dnsmasq
        ├── identity: DHCP · neighbours · mDNS · DNS-SD · NetBIOS · SSDP · Pi-hole · OUI
        ├── local metadata: SQLite
        └── services: Docker · Pi-hole · WireGuard · Caddy
```

There are no external runtime assets. Product metadata and version come from `project.json`.

More detail: **[Architecture notes](docs/architecture.md)**.

## API

```text
GET   /api/v1/meta
GET   /api/v1/health
GET   /api/v1/status
GET   /api/v1/host
GET   /api/v1/network
GET   /api/v1/devices
GET   /api/v1/baseline
POST  /api/v1/baseline
DELETE /api/v1/baseline
GET   /api/v1/devices/{id}
PATCH /api/v1/devices/{id}/metadata
GET   /api/v1/devices/{id}/presence?limit=50
DELETE /api/v1/devices/{id}/memory
POST  /api/v1/devices/{id}/wake
POST  /api/v1/devices/{id}/probe
GET   /api/v1/devices/{id}/services?limit=10
POST  /api/v1/devices/{id}/services/scan
GET   /api/v1/activity?limit=50
GET   /api/v1/monitor
GET   /api/v1/notifications
POST  /api/v1/notifications/test
GET   /api/v1/integrations/home-assistant
GET   /api/v1/services
GET   /api/v1/services/{id}
GET   /api/v1/diagnostics
GET   /metrics
```

Normal dashboard refreshes use the aggregated status endpoint. Discovery is cached briefly and subprocesses are executed as literal argument lists with bounded timeouts; AuraLAN does not expose an arbitrary shell endpoint.

## Privacy and security

Runtime network information stays on the machine running AuraLAN. Device identity is not sent to external lookup services.

The Prometheus endpoint intentionally exposes aggregate counts and host-health gauges only. It does not emit device names, IDs, IP/MAC addresses, notes, or per-device labels.

Webhook delivery is disabled unless explicitly configured. Event payloads omit IP/MAC/internal device IDs by default; the endpoint URL and optional bearer token are never exposed through the browser-facing status, diagnostics, or Prometheus surfaces.

The production systemd example binds to loopback by default. Remote LAN access should be an explicit choice, typically through a reverse proxy or by changing `AURALAN_HOST`.

Repository hygiene and disclosure guidance: **[SECURITY.md](SECURITY.md)**.

## Branches

`main` is kept release-ready. Ongoing integration belongs on `dev`; short-lived feature and fix branches should be removed after merge.

## Development and validation

```bash
python3 scripts/validate-release.py
python3 scripts/audit-history.py

cd backend
.venv/bin/python -m unittest discover -s tests -v

cd ..
node --test frontend/tests/*.test.mjs
```

CI performs repository hygiene checks, reachable-history secret scanning, dependency auditing, backend tests, frontend syntax checks and frontend unit tests.

For a full check on the actual Linux/Raspberry Pi host, including an isolated HTTP boot and a fresh device-identification report:

```bash
./scripts/local-release-check.sh
```

The local check uses temporary AuraLAN state for the isolated instance, so it does not overwrite the installed device-alias database.

## Project status

AuraLAN 1.0.0 is the first stable release line. `main` is kept release-ready, while `dev` remains the integration branch for post-1.0 work. The 1.0 product includes Activity Center, Network Baseline, local Identity Intelligence, persistent inventory and presence history, Home Assistant integration, Wake-on-LAN, on-demand reachability checks and local Service Exposure snapshots. The v1 API remains intentionally small and local-first.

User-facing changes are tracked in **[CHANGELOG.md](CHANGELOG.md)**.

## Contributing

Contributions are welcome when they preserve AuraLAN's local-first, evidence-based design. Read **[CONTRIBUTING.md](CONTRIBUTING.md)** before changing discovery, identity or icon inference.

## License

AuraLAN is released under the [MIT License](LICENSE).
