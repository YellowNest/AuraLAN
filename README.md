<p align="center">
  <img src="frontend/assets/icons/logo-mark.svg" width="128" height="128" alt="AuraLAN logo">
</p>

<h1 align="center">AuraLAN</h1>

<p align="center">
  <strong>Your network, clearly.</strong><br>
  A local-first network console for Linux and Raspberry Pi.
</p>

<p align="center">
  <a href="https://github.com/YellowNest/AuraLAN/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/YellowNest/AuraLAN/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB">
  <img alt="Local first" src="https://img.shields.io/badge/data-local--first-22C55E">
  <img alt="No telemetry" src="https://img.shields.io/badge/telemetry-none-64748B">
</p>

AuraLAN turns the network state already available on a Linux host into a focused dashboard for people who want to understand their LAN without living in terminals.

It answers the useful questions first: **what is connected, what each device probably is, whether it is online, how it was discovered, and which local services need attention.**

## Why AuraLAN

| | |
|---|---|
| **Human-readable devices** | Combines DHCP, neighbours, Wi-Fi station data, local names and service discovery into conservative device identities. |
| **A device inventory that remembers** | Track first/last seen time, add aliases, keep private notes, mark important devices, filter new devices, review recent discoveries, keep previously seen devices visible, and export the inventory as CSV or JSON. |
| **Runs even when the dashboard is closed** | Continuous local discovery refreshes the inventory and history in the background instead of depending on an open browser tab. |
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
- local/offline OUI registries installed on the host

Device identity is deliberately conservative. An OUI can identify an organization; it cannot prove an exact model. AuraLAN keeps the raw evidence separate from the friendly presentation.

### Device inventory

AuraLAN remembers when a device was first and last observed. You can give devices your own names, keep a short local note and mark important devices as favorites. Favorites also act as a lightweight local watchlist: if a favorite is only present in remembered inventory and has no current observation, AuraLAN surfaces that on Overview without claiming the device is definitely offline. The device view can surface favorites, newly seen devices, connection type and devices that still need a better identity.

Once AuraLAN has observed a device, it also keeps a compact last-known presentation in local state. If the device later disappears from the current discovery pass it remains searchable as **Not seen now**, with its last-seen time and last-known identity instead of silently vanishing from the inventory.

All of that inventory data stays in AuraLAN's local SQLite state. AuraLAN also keeps a compact first-seen discovery history, so the Overview can answer "what showed up recently?" without sending device data anywhere. Existing installations backfill this history from their already stored first-seen timestamps, so upgrading does not start with an empty timeline.

A background monitor performs local discovery every 60 seconds by default, so first/last-seen data, recent discoveries and the favorite-device watchlist continue updating when the web interface is closed. The interval is configurable or can be disabled entirely.

A "new" device means **new to this AuraLAN installation within the last 24 hours**; it is an observation aid, not an intrusion verdict. Recent-discovery entries are likewise local observations, not security alerts.

The Devices view can export the current inventory as CSV or JSON directly in the browser. Exports can contain private IP/MAC addresses and user notes, so AuraLAN labels that clearly before download. CSV cells that begin like spreadsheet formulas are neutralized before export because network-provided device names are not trusted input.

## What AuraLAN does not do

AuraLAN is not a router, firewall, DHCP server, DNS server, Wi-Fi controller, VPN server or Docker manager.

The current release does **not** change host networking, firewall rules, DHCP, DNS, Docker, Caddy, Pi-hole or WireGuard. Writes are limited to AuraLAN's own local state: observed device identity/presence, recent-discovery history, and user-owned metadata such as aliases, notes and favorites.

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
- service/deployment overrides

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
GET   /api/v1/devices/{id}
PATCH /api/v1/devices/{id}/metadata
GET   /api/v1/activity?limit=50
GET   /api/v1/monitor
GET   /api/v1/services
GET   /api/v1/services/{id}
GET   /api/v1/diagnostics
GET   /metrics
```

Normal dashboard refreshes use the aggregated status endpoint. Discovery is cached briefly and subprocesses are executed as literal argument lists with bounded timeouts; AuraLAN does not expose an arbitrary shell endpoint.

## Privacy and security

Runtime network information stays on the machine running AuraLAN. Device identity is not sent to external lookup services.

The Prometheus endpoint intentionally exposes aggregate counts and host-health gauges only. It does not emit device names, IDs, IP/MAC addresses, notes, or per-device labels.

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

AuraLAN `0.4.0` is the first public pre-1.0 release. The API is intentionally small and may still evolve before 1.0.

User-facing changes are tracked in **[CHANGELOG.md](CHANGELOG.md)**.

## Contributing

Contributions are welcome when they preserve AuraLAN's local-first, evidence-based design. Read **[CONTRIBUTING.md](CONTRIBUTING.md)** before changing discovery, identity or icon inference.

## License

AuraLAN is released under the [MIT License](LICENSE).
