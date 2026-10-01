# Changelog

All notable user-facing changes to AuraLAN are tracked here.

AuraLAN follows Semantic Versioning. During the pre-1.0 phase, minor versions may still contain compatibility changes. The canonical version lives in `project.json`; a `-dev` suffix means the version is still under development.

## [Unreleased]

### Changed

- Device list presentation is now tuned as one responsive system: iPhone rows keep device name, identity, full IP and full MAC readable in a compact three-line hierarchy, while wide desktops gain a stable dedicated MAC column and intermediate widths collapse cleanly without clipping.

### Added

- **On-demand device reachability checks** add a one-click ICMP probe in the device inspector. AuraLAN sends one local echo request to a known IPv4 address, reports round-trip latency when a reply is available, hides the action when the host has no `ping` utility, and never treats a missing ICMP reply as proof that the device is offline.
- README discovery wording now describes AuraLAN as a self-hosted LAN inventory and network monitoring console, making the project's purpose clearer to people searching GitHub for Raspberry Pi and local network tooling.

### Fixed

- Background monitoring now reuses a just-completed cached snapshot instead of forcing an identical back-to-back full discovery pass when dashboard/API polling happens at the same time, removing avoidable CPU and subprocess bursts.
- mDNS, resolver, and NetBIOS caches now expire entries independently and use a hard size bound, preventing long-running device/MAC churn from extending stale entries or growing process memory indefinitely while still retaining short-lived disappear/reappear cache hits.
- Pi-hole FTL identity enrichment now queries only MAC/IP identities AuraLAN already knows and caps cached result rows, avoiding a recurring full historical network-table read on long-running Pi-hole installations.
- Persistent first-seen history backfill now uses one indexed set-based SQLite statement instead of running a NOT EXISTS query once per current device on every inventory refresh.
- Dashboard polling pauses while the browser tab is hidden and refreshes immediately when it becomes visible again, avoiding unnecessary discovery work from inactive tabs.
- Reachability checks no longer display a fabricated `0 ms` latency when ping succeeded but the local ping output did not contain a parsable timing value.
- The README project-status section no longer claims that 0.7.0 is the current code line after the 0.8.0 release commit landed.

## [0.8.0] - 2026-10-01

### Added

- **Network Baseline** lets users capture the devices AuraLAN can see now and then highlights additions and absences against that local reference point. Matching uses all known MAC identities for multi-interface devices, stays entirely local, and deliberately reports change rather than making a security verdict.

## [0.7.0] - 2026-09-30

### Added

- **Identity Intelligence** gives the Devices view a local identity-coverage score, evidence strength, readable discovery-source chips and a dedicated filter for devices that still need identification.
- Device identity can now use the systemd/udev offline OUI hardware database in addition to ieee-data, nmap and arp-scan registries, improving manufacturer coverage on common Linux installations without any cloud lookup.
- HomeKit accessory-category hints, Matter service signatures, Apple Companion-Link model metadata, NAS signatures and Android/Google TV signatures add standards-based local evidence for friendlier device classification.

### Fixed

- Model-only SSDP identities now preserve SSDP as their evidence source instead of being mislabeled as cache-derived.

- The IPv4 default gateway is now identified as a **Router** with router iconography and shown as the **Default gateway** connection instead of looking like an ordinary device merely seen via the router; manual category overrides still take precedence.
- Webhook `pending_events` now counts actual persisted events after the delivery cursor instead of subtracting SQLite event IDs, so forgetting a device cannot make deleted event-ID gaps appear as phantom pending notifications.

## [0.6.0] - 2026-09-29

### Fixed

- The Home Assistant aggregate summary now counts only services actually detected by AuraLAN, matching the Prometheus metric and the field's documented meaning.

### Added

- Remembered **Not seen now** devices can now be explicitly forgotten from the device inspector. AuraLAN removes its own saved inventory, identity, metadata, activity, watch state and presence history transactionally; currently observed devices are protected from accidental forgetting.
- Home Assistant now has a dedicated aggregate REST summary endpoint with device/service counts, monitor health, webhook state and Wake-on-LAN capability while deliberately excluding per-device identity data; ready-to-adapt REST and webhook examples are documented separately.
- Per-device presence history now records debounced **Not seen** and **Seen again** transitions in bounded local SQLite state, with a dedicated API and timeline in the device inspector. A single weak discovery miss is ignored by default.
- Optional Wake-on-LAN can now be enabled explicitly for known devices. AuraLAN sends one validated UDP magic packet, prefers a globally administered unicast MAC when multiple NICs are known, and keeps the action disabled by default.
- Device inventory organization now supports a local location field and up to eight lightweight tags per device. Locations and tags participate in search, survive remembered-device state, and are included in CSV/JSON exports.
- The Devices view now offers persistent sorting by smart order, name, last seen, first seen, location or IP address.

## [0.5.0] - 2026-09-29

### Fixed

- The aggregate status endpoint now includes AuraLAN and API version metadata, matching health/diagnostics and making release verification self-contained.
- Favorite-device absence events are now debounced with a persistent grace period, preventing one transient discovery miss from producing a `favorite_not_seen` webhook or activity event while still reporting a confirmed return immediately.
- Clean systemd installs now build in an isolated staging directory and remove an incomplete activation automatically, so dependency or first-start failures are safe to retry.
- Git-backed install and upgrade sources now refuse dirty worktrees, preventing validation from checking files that differ from the archived commit.
- Upgrade readiness now opens a consistent copy of the current AuraLAN SQLite state with the staged release before code is switched, while the runtime health endpoint verifies metadata-store readiness after activation.
- Interrupted-upgrade markers are diagnosed before the upgrader can misreport the installation as missing, and activation rollback keeps restoring the previous application, unit and database state.
- CI now includes a generic Linux smoke boot that exercises the full status API as well as the state-aware health endpoint.
- Concurrent cache misses now collapse into one discovery pass, and cache age starts when collection completes rather than before a slow refresh.
- SQLite state now re-bootstraps its schema after a database replacement and metadata write failures return a controlled service-unavailable response instead of leaking an internal error.
- NetworkManager terse output now honors escaped delimiters in connection names and SSIDs.
- Ordinary Linux hosts are no longer marked unhealthy merely because their Wi-Fi interface is a client rather than an access point; AP mode becomes an explicit expectation only when `AURALAN_WIFI_INTERFACE` is configured.
- dnsmasq is no longer treated as AuraLAN's DHCP source unless it is explicitly scoped to the confirmed access-point interface, preventing unrelated local DNS-cache instances from contributing misleading lease data.

### Added

- Optional reliable HTTP(S) webhook notifications can now deliver new-device and favorite-watch state events to Home Assistant or another receiver. Delivery is ordered, failed events remain pending for retry, old history is not replayed on first enable, and IP/MAC/internal device IDs are excluded unless explicitly opted in.
- Settings exposes webhook delivery health and a test action without revealing the configured URL or bearer token; aggregate delivery state is also available through diagnostics and Prometheus.
- AuraLAN now performs continuous local discovery in the background by default, keeping inventory, first/last-seen timestamps, discovery history and favorite-device watch state current even when no browser is open; the interval is configurable and can be disabled.
- Settings, diagnostics, Prometheus and `/api/v1/monitor` expose background-monitor health without including device identity data.
- Favorite devices now double as a local watchlist: Overview highlights favorites that AuraLAN is not currently observing, and the Devices view can filter that exact state without calling the device offline.
- Device discovery history now backfills from existing first-seen inventory data, adds a full local history inspector, and supports requesting up to 100 entries from `/api/v1/activity`.
- A dependency-free Prometheus `/metrics` endpoint now exposes aggregate inventory, service and host-health gauges without device identities, addresses or notes.
- The Devices view can export the current local inventory as CSV or JSON in-browser, with an explicit privacy warning and spreadsheet-formula neutralization for untrusted network-provided values.
- The Network view now includes an evidence-based map that groups current devices by confirmed Wi-Fi, Ethernet, VPN or other connection evidence and links each visible node back to its device details.
- Previously observed devices now remain in the inventory as **Not seen now** when they are absent from the current discovery pass, preserving last-known identity, addressing and presence data without pretending absence proves the device is offline.
- The Devices view adds a dedicated remembered-device filter while live devices with overlapping MAC identities suppress their historical copy.
- AuraLAN now keeps a compact local first-seen discovery history and shows recent device discoveries on Overview.
- Device aliases update matching discovery labels, while multi-interface devices only generate a discovery when all observed identities are new, reducing false "new device" entries for an existing machine gaining another adapter.
- Device inventory now exposes first/last-seen timestamps, local notes and favorites in the device inspector.
- Device search includes local notes, and the device view can filter favorites and devices first seen by AuraLAN within the last 24 hours.
- The overview surfaces newly seen devices without treating them as a security verdict; inventory data remains local to AuraLAN.
- Canonical systemd installations now have a staged production upgrader that preserves host configuration and runtime state, creates a consistent SQLite backup, health-checks the new version, and restores code/unit/database state automatically on activation failure.

### Changed

- User-owned runtime state now defaults to the per-user XDG state directory outside the source checkout when AuraLAN is run without an explicit `AURALAN_DATA_DIR`; the supplied systemd service continues to use `/var/lib/auralan`.
- Documentation now makes the separation between application code, local runtime data, and host-specific configuration explicit so updates cannot accidentally package another user's settings.

## [0.4.0] - 2026-09-29

### Added

- Portable AP detection across all NetworkManager Wi-Fi connections and direct `iw` interfaces, with an optional `AURALAN_WIFI_INTERFACE` override.
- Production installation, configuration, compatibility, support, and release-checklist documentation.
- Canonical `auralan.service` environment overrides with loopback-only binding by default.
- GitHub issue and pull-request templates that explicitly protect private LAN data.
- Leaner production dependencies by removing the unused YAML library.
- Clean systemd installer with an unprivileged service account, local-file exclusion, health verification, and loopback-only default exposure.
- Public service packaging and local deployment use the canonical `auralan.service`.
- CI coverage for Python 3.11 and 3.13, frontend Node 24, shell syntax, dependency consistency, Python bytecode compilation, and known-vulnerability auditing.
- FastAPI, Uvicorn, and Pydantic updated from the original development pins to current stable release-line versions.

- Deeper local identity correlation via the configured host resolver, NetBIOS, SSDP/UPnP friendly names, Pi-hole FTL history when available, and a persistent same-MAC identity cache.
- Product-family icon normalization driven by local evidence, including Apple TV, robot vacuums, garage doors, heat pumps, and VR headsets.
- Heat-pump names can now contribute a generic smart-home category without requiring a vendor-specific rule.
- Full-screen mobile inspector layout with safe-area handling and a persistent close action.
- Manufacturer + MAC identity in mobile device rows.
- Contributor guidance for identity rules, UI changes, testing, and release hygiene.

### Fixed

- Removed obsolete service-name compatibility; release validation rejects retired branding anywhere in tracked text.

- Avahi DNS-SD browsing now disables the human service-type database so parsable output contains stable raw service types such as `_airplay._tcp`.
- Human-facing Apple service instance names are preserved even when they match the device hostname.

- DNS-SD parsing now decodes Avahi decimal escapes as UTF-8 bytes, handles escaped literal punctuation, strips machine-generated instance prefixes, and extracts only the human label from Apple Sleep Proxy instance names.

- Local discovery subprocess output now uses replacement decoding so malformed device-supplied UTF-8 cannot abort DNS-SD/mDNS enrichment.

### Changed

- Brand fallback metadata is now validated against `project.json`, including accent tokens.
- Generic test fixtures no longer use conventional Linux interface names.
- Added a full local release check that validates `main`, boots an isolated AuraLAN instance, exercises HTTP endpoints, and prints fresh device-identification evidence without modifying installed AuraLAN metadata.

- Removed deployment-specific Pi-hole filesystem assumptions; non-standard FTL locations now use `AURALAN_PIHOLE_FTL_DB`.
- Removed the unused YAML configuration placeholder so documented configuration matches actual runtime behavior.
- Repository presentation and release validation now enforce portable examples and block known local/private fixtures.

- Rotated-phone device lists now reserve enough width for full IP addresses and keep status indicators circular instead of collapsing under tight landscape columns.
- Devices with the same trusted computer/server/printer hostname can now collapse into one physical-device entry across multiple network adapters; all observed MAC and IP addresses remain available in details/search.
- Unresolved locally administered MAC addresses are labeled explicitly instead of looking like ordinary vendor-resolvable devices.
- Mobile device filters now stay single-line; the naming-review action is separated from connection/status filters.
- Apple TV devices use a locally rendered Apple TV brand mark instead of the generic television/play glyph.
- Robot-vacuum recognition now considers resolved vendor identity, so Roborock/iRobot/Ecovacs-family devices do not fall back to the generic smart-home icon.
- Product-specific icon selection remains separate from exact-model inference: AuraLAN still does not guess a hardware model from an OUI.

Formal release history starts with the first public AuraLAN release.
