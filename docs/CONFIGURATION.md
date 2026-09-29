# Configuration

AuraLAN discovers the host dynamically and avoids machine-specific configuration where possible.

Production overrides can be placed in `/etc/default/auralan`. Development commands can export the same variables directly.

| Variable | Default | Purpose |
|---|---|---|
| `AURALAN_HOST` | `127.0.0.1` in supplied scripts/unit | HTTP bind address |
| `AURALAN_PORT` | `8787` | HTTP port |
| `AURALAN_DATA_DIR` | `/var/lib/auralan` | AuraLAN-owned SQLite/runtime state |
| `AURALAN_WIFI_INTERFACE` | automatic | Prefer one wireless interface when several exist |
| `AURALAN_PIHOLE_FTL_DB` | standard Pi-hole paths | Explicit path to a readable Pi-hole FTL database |
| `AURALAN_OUI_FILE` | standard Linux OUI paths | Explicit local/offline OUI registry |
| `AURALAN_SERVICE` | auto-detected | Service name used by the local deployment helper |
| `AURALAN_HEALTH_URL` | `http://127.0.0.1:8787/api/v1/health` | Deployment health-check URL |
| `AURALAN_URL` | `http://127.0.0.1:8787` | Browser sanity-test target |

## Wi-Fi interface selection

Normally no override is required. AuraLAN examines all active NetworkManager Wi-Fi connections and all interfaces reported by `iw`, then confirms AP mode with `iw`.

If a host has unusual wireless topology:

```bash
AURALAN_WIFI_INTERFACE=hotspot0
```

The name is an override, not a built-in assumption.

## Pi-hole FTL

AuraLAN checks standard local Pi-hole database locations. For a custom installation:

```bash
AURALAN_PIHOLE_FTL_DB=/path/to/pihole-FTL.db
```

The file is opened read-only.

## Local data

AuraLAN stores only its own metadata, such as user aliases and observation timestamps, in its SQLite database. Set a custom location with:

```bash
AURALAN_DATA_DIR=/srv/auralan
```

Do not place credentials in the repository. Environment overrides containing private paths or deployment-specific values belong on the host.

## Offline OUI registry

AuraLAN never requires an online MAC-vendor service. It reads common Linux OUI database locations automatically.

For a custom local registry:

```bash
AURALAN_OUI_FILE=/path/to/oui.txt
```

Unknown prefixes remain unknown rather than triggering a cloud lookup.
