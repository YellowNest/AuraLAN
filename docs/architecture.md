# Architecture notes

## Discovery boundaries

Discovery adapters return normalized data and do not know about markup or browser state.

- `network/iproute.py` identifies routes, addressable interfaces, and conservative presentation roles.
- `network/networkmanager.py` finds active connections.
- `network/iw.py` confirms AP mode and optionally reads associated-station signal.
- `network/dnsmasq.py` associates an active dnsmasq unit with the AP interface before reading its lease file.
- `network/devices.py` merges only AP/uplink-relevant neighbour records with the AP lease source.
- `integrations/` exposes the same service shape for Docker, Caddy, Pi-hole, and WireGuard.

Every adapter is read-only. `services/system.py` catches a failing subsystem, records a sanitized discovery error, and still returns the remaining snapshot.

## Identity evidence

Device identity is assembled from independently collected local evidence rather than from a cloud fingerprinting service. Host names, DNS-SD/mDNS, SSDP/UPnP descriptions, DHCP, NetBIOS, Pi-hole history, route roles and offline OUI registries remain separate evidence sources. HomeKit category metadata and Matter service advertisements contribute broad device-class hints without claiming an exact hardware model.

AuraLAN also reads the host's systemd/udev OUI hardware database when present, in addition to conventional ieee-data, nmap and arp-scan registries. The frontend's Identity Intelligence score describes how complete the locally observed identity is; it is not a probability or a claim that an inferred model is correct.

## Health state

`healthy` means AuraLAN completed its available local discovery without a reported provider error and no detected service is offline. An absent optional integration is neutral. A detected but offline service is `degraded`; a partial discovery failure is `warning`. Access-point mode is only treated as an explicit expectation when `AURALAN_WIFI_INTERFACE` is configured, so an ordinary Linux host acting as a Wi-Fi client is not marked unhealthy merely because it is not an AP.

## Frontend

The frontend is deliberately framework-free native ES modules. `app.js` owns route and client preference state; `i18n.js`, `icons.js`, and `brand.js` centralize shared UI definitions. The status API remains the single refresh request for normal navigation. A detail panel requests diagnostics only on user action.

## Caching

The backend caches an aggregate discovery result for two seconds. API responses are sent with `Cache-Control: no-store`. During pre-release development, the service-worker endpoint is a recovery worker: it clears old AuraLAN caches and unregisters itself. This avoids a stale app shell surviving an API-contract change; offline caching will return only with content-hashed production assets.
