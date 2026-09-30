# Compatibility

AuraLAN is provider-based: the application remains usable when optional discovery sources are absent.

| Capability | Source | Required? |
|---|---|---|
| Host health | Linux `/proc`, filesystem | Core |
| Routes/interfaces | iproute2 | Recommended |
| AP confirmation | `iw` | Required for confirmed AP status |
| NetworkManager metadata | `nmcli` | Optional |
| DHCP leases | dnsmasq | Optional |
| Local hostname lookup | host resolver / `getent` | Optional |
| mDNS / DNS-SD | Avahi | Optional |
| NetBIOS names | `nmblookup` | Optional |
| SSDP / UPnP | local UDP/HTTP | Optional |
| Docker status | Docker CLI/socket | Optional |
| Pi-hole | service/container + optional FTL DB | Optional |
| MAC vendor names | local systemd/udev hwdb or ieee-data/nmap/arp-scan OUI registry | Optional |
| WireGuard | kernel interfaces / `wg` | Optional |
| Caddy | systemd or Docker | Optional |

## Interface names

AuraLAN does not require conventional interface names. Interface names are discovered at runtime.

## NetworkManager

NetworkManager is not required for AP detection. If it is installed, AuraLAN uses its active-connection metadata. The actual AP role is still confirmed independently through `iw`.

## Failure behavior

A missing optional binary or unreadable optional integration should result in unavailable/unknown data for that provider, not an empty dashboard.

## Architectures

The codebase is pure Python plus browser JavaScript and has no architecture-specific application binaries. It is intended to work on common Linux architectures supported by the Python dependencies, including Raspberry Pi ARM systems and x86-64 Linux.
