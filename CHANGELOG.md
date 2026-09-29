# Changelog

All notable user-facing changes to AuraLAN are tracked here.

AuraLAN follows Semantic Versioning. During the pre-1.0 phase, minor versions may still contain compatibility changes. The canonical version lives in `project.json`; a `-dev` suffix means the version is still under development.

## [Unreleased]

Development target: `0.4.1`.

### Fixed

- Clean systemd installs now build in an isolated staging directory and remove an incomplete activation automatically, so dependency or first-start failures are safe to retry.
- Git-backed install and upgrade sources now refuse dirty worktrees, preventing validation from checking files that differ from the archived commit.
- Upgrade readiness now opens a consistent copy of the current AuraLAN SQLite state with the staged release before code is switched, while the runtime health endpoint verifies metadata-store readiness after activation.
- Interrupted-upgrade markers are diagnosed before the upgrader can misreport the installation as missing, and activation rollback keeps restoring the previous application, unit and database state.
- CI now includes a generic Linux smoke boot that exercises the full status API as well as the state-aware health endpoint.
- Concurrent cache misses now collapse into one discovery pass, and cache age starts when collection completes rather than before a slow refresh.
- SQLite state now re-bootstraps its schema after a database replacement and metadata write failures return a controlled service-unavailable response instead of leaking an internal error.
- NetworkManager terse output now honors escaped delimiters in connection names and SSIDs.

### Added

- The Network view now includes an evidence-based map that groups current devices by confirmed Wi-Fi, Ethernet, VPN or other connection evidence and links each visible node back to its device details.
- Previously observed devices now remain in the inventory as **Not seen now** when they are absent from the current discovery pass, preserving last-known identity, addressing and presence data without pretending absence proves the device is offline.
- The Devices view adds a dedicated remembered-device filter while live devices with overlapping MAC identities suppress their historical copy.
- AuraLAN now keeps a compact local first-seen discovery history and shows recent device discoveries on Overview.
- Device aliases update matching discovery labels, while multi-interface devices only generate a discovery when all observed identities are new, reducing false "new device" entries for an existing machine gaining another adapter.
- Device inventory now exposes first/last-seen timestamps, local notes and favorites in the device inspector.
- Device search includes local notes, and the device view can filter favorites and devices first seen by AuraLAN within the last 24 hours.
- The overview surfaces newly seen devices without treating them as a security verdict; inventory data remains local to AuraLAN.
- Canonical systemd installations now have a staged production upgrader that preserves host configuration and runtime state, creates a consistent SQLite backup, health-checks the new version, and restores code/unit/database state automatically on activation failure.

### Fixed

- Ordinary Linux hosts are no longer marked unhealthy merely because their Wi-Fi interface is a client rather than an access point; AP mode becomes an explicit expectation only when `AURALAN_WIFI_INTERFACE` is configured.
- dnsmasq is no longer treated as AuraLAN's DHCP source unless it is explicitly scoped to the confirmed access-point interface, preventing unrelated local DNS-cache instances from contributing misleading lease data.

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
