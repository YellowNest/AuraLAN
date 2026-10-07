# Docker

AuraLAN has an official Linux container image at `ghcr.io/yellownest/auralan`.

The image supports `linux/amd64` and `linux/arm64`. Raspberry Pi 4/5 running a 64-bit OS therefore uses the same image as other Linux hosts.

## Start

From the repository:

```bash
docker compose up -d
```

Open:

```text
http://HOST-IP:8787
```

Persistent AuraLAN state is kept in the named `auralan-data` volume.

Upgrade with:

```bash
docker compose pull
docker compose up -d
```

## Why host networking is used

AuraLAN is a network-observation application. A normal Docker bridge gives the process a container-specific routing table, neighbour table and interfaces, which would make LAN inventory misleading.

The supplied Compose file therefore uses:

```yaml
network_mode: host
```

On Linux this lets AuraLAN observe the host network namespace while keeping the application filesystem and persistent state isolated in the container.

The default deployment does **not** use `privileged: true`.

## Default security model

The supplied Compose file:

- runs AuraLAN as an unprivileged UID/GID (`10001:10001`)
- drops all Linux capabilities, then adds only `NET_RAW` for bounded ICMP reachability checks
- enables `no-new-privileges`
- makes the container root filesystem read-only
- gives AuraLAN one writable persistent volume at `/data`
- uses a small temporary `/tmp`
- mounts host `/proc`, `/sys`, hostname and hosts data read-only
- does not mount the Docker socket or system D-Bus by default

The `/proc` and `/sys` mounts are used for host uptime, memory and thermal readings. Host root filesystem usage is intentionally not exposed by the default container because doing that would require a broad host-root bind mount.

## Discovery available in the default container

With host networking AuraLAN can use the host network namespace for route, interface and neighbour discovery. The image also includes the local tools used by AuraLAN: `ip`, `ping`, `iw`, `nmcli`, Avahi utilities, NetBIOS utilities and `wg`.

Some tools depend on host services that live outside the container. Those integrations stay optional and fail independently, exactly like a native AuraLAN installation.

### Wi-Fi station details

Most network inventory works without `NET_ADMIN`. Some Linux wireless drivers restrict station telemetry such as signal strength to processes with `CAP_NET_ADMIN`.

Only if that information is required, add this explicitly:

```yaml
services:
  auralan:
    cap_add:
      - NET_RAW
      - NET_ADMIN
```

`NET_ADMIN` is deliberately not enabled by default because host networking makes that capability powerful.

### NetworkManager and Avahi

`nmcli`, `avahi-browse` and `avahi-resolve-address` normally communicate with host daemons over the system D-Bus. The default container does not receive that socket.

If NetworkManager/DNS-SD enrichment is required and the host policy permits it, add:

```yaml
services:
  auralan:
    volumes:
      - /run/dbus/system_bus_socket:/run/dbus/system_bus_socket:ro
```

This is optional. A D-Bus mount increases host integration and therefore the security impact of a compromised container.

## Docker service visibility

AuraLAN does not mount the Docker daemon socket by default. Access to that socket is highly privileged even when the bind mount itself is marked read-only.

AuraLAN can query the Docker Engine API with bounded read-only requests when `AURALAN_DOCKER_SOCKET` is explicitly configured.

An opt-in Compose overlay is provided:

```bash
export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
docker compose -f compose.yaml -f compose.docker-socket.yaml up -d
```

The overlay:

- mounts `/var/run/docker.sock`
- adds only the host socket's group ID to the AuraLAN process
- sets `AURALAN_DOCKER_SOCKET=/var/run/docker.sock`

Treat Docker-socket access as host-level trust. Do not enable it merely to remove a harmless "Docker unavailable" message.

## Pi-hole FTL enrichment

If Pi-hole runs on the host, mount its database directory read-only and point AuraLAN at the mounted database. Example for the common path:

```yaml
services:
  auralan:
    environment:
      AURALAN_PIHOLE_FTL_DB: /host/pihole/pihole-FTL.db
    volumes:
      - /etc/pihole:/host/pihole:ro
```

Mount the directory rather than only the SQLite file so SQLite can see companion WAL/SHM files when the host database uses them.

## Host storage usage

The default container intentionally reports host storage usage as unavailable instead of showing the container overlay filesystem and pretending it is the host disk.

If an operator explicitly wants host filesystem usage, mount only the filesystem that should be measured and set `AURALAN_HOST_ROOT` to that mount. Avoid mounting the entire host root unless the deployment genuinely requires it.

## Image tags

`main` is release-ready, so successful pushes to `main` publish:

- `ghcr.io/yellownest/auralan:latest`
- a commit-SHA tag

Semantic Git tags such as `v1.6.0` additionally publish:

- `1.6.0`
- `1.6`
- `1`

The GitHub Actions build publishes a multi-architecture manifest for AMD64 and ARM64 together with SBOM and provenance attestations.

For reproducible deployments, pin a version tag instead of `latest` after an official versioned image has been published.
