# Installation

AuraLAN is a local Linux application. It reads host/network state and serves the frontend from the same FastAPI process.

## Requirements

Core runtime:

- Linux
- Python 3.11 or newer
- iproute2 recommended for network/interface discovery

Optional capabilities appear automatically when the relevant local tool or service is available:

- `iw` — Wi-Fi/AP mode and station signal
- NetworkManager / `nmcli` — active Wi-Fi connection metadata
- dnsmasq — DHCP lease context
- Avahi — mDNS and DNS-SD names
- Samba tools / `nmblookup` — NetBIOS names
- Docker — container/service visibility
- Pi-hole — service state and optional FTL identity history
- WireGuard / `wg` — VPN state
- Caddy — reverse-proxy state

Missing optional tools do not prevent AuraLAN from starting.

## Development or evaluation

```bash
git clone https://github.com/YellowNest/AuraLAN.git
cd AuraLAN
./scripts/dev.sh
```

The default bind address is loopback:

```text
http://127.0.0.1:8787
```

To expose the development server directly on your LAN:

```bash
AURALAN_HOST=0.0.0.0 ./scripts/dev.sh
```

Direct LAN exposure is convenient for testing but should be an explicit choice.

## One-command systemd install

From a clean reviewed checkout:

```bash
sudo ./scripts/install.sh
```

The installer deliberately performs **clean installs only**. It refuses to overwrite a populated `/opt/auralan`, excludes local runtime/credential files when installing from a non-Git source tree, creates a dedicated unprivileged service account, installs dependencies inside AuraLAN's own virtual environment, installs the canonical systemd unit, starts it bound to loopback, and waits for the health endpoint before reporting success.

It does not change Docker permissions, Pi-hole permissions, firewall rules, Wi-Fi, DHCP, DNS, or reverse-proxy configuration.

## Production layout

The supplied unit keeps application code, user-owned runtime state, and host-specific configuration separate:

```text
/opt/auralan           application code
/var/lib/auralan       AuraLAN-owned runtime data and local device metadata
/etc/default/auralan   optional host-specific environment overrides
```

Updating or replacing the application code does not require copying `/var/lib/auralan` into the repository. User aliases, observation history, and identity cache data remain local to that installation. Likewise, host-specific overrides in `/etc/default/auralan` are outside the source tree and are not part of Git merges.

Create a dedicated service account, copy a reviewed release checkout into `/opt/auralan`, create the virtual environment, then install `systemd/auralan.service`.

The commands below assume the AuraLAN files have already been copied to `/opt/auralan`.

Example:

```bash
sudo useradd --system --user-group --home /var/lib/auralan --shell /usr/sbin/nologin auralan
sudo mkdir -p /opt/auralan
sudo chown -R auralan:auralan /opt/auralan

sudo -u auralan python3 -m venv /opt/auralan/backend/.venv
sudo -u auralan /opt/auralan/backend/.venv/bin/pip install -r /opt/auralan/backend/requirements.txt

sudo cp systemd/auralan.service /etc/systemd/system/auralan.service
sudo systemctl daemon-reload
sudo systemctl enable --now auralan.service
```

## Access from other devices

The production unit binds to `127.0.0.1` by default.

Recommended: place a local reverse proxy in front of AuraLAN. A Caddy example is provided in `caddy/Caddyfile.ap.example`.

Alternatively create `/etc/default/auralan`:

```bash
AURALAN_HOST=0.0.0.0
AURALAN_PORT=8787
```

Then:

```bash
sudo systemctl restart auralan
```

## Optional permissions

AuraLAN intentionally does not grant itself broad privileges.

Docker discovery requires the service account to be able to query the Docker daemon. Pi-hole FTL enrichment requires read access to the selected database. Grant only the minimum permission required on systems where you want those integrations.

Do not make the service root merely to unlock optional integrations.

## Existing development installations

The repository ships only the canonical `auralan.service`. Development checkouts should keep runtime state outside the checkout and use `AURALAN_DATA_DIR` when a custom state location is needed.
