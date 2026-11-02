# AuraLAN 2.0 — scope and continuing roadmap

AuraLAN 2.0.0 ships an evidence-preserving LAN console upgrade with scalable inventory, subnet/VLAN display, explicit local TCP checks, management shortcuts, and Activity accessibility. The remaining items are a roadmap for later 2.x releases, not claims about shipped 2.0.0 capabilities.

## Research-informed demand

- Accurate, automatically refreshed network maps, including explicit unknown connections rather than fabricated switch and Wi-Fi associations.
- Easy device inventory, names and service links, LAN/VLAN context, portable exports and meaningful online status.
- Opt-in, actionable device/service alerts with transparent timestamps and low maintenance.
- Self-hosted Docker/Raspberry Pi deployment, accessible mobile dashboard and low resource use without mandatory cloud services.

Evidence includes r/selfhosted requests for a network diagram plus status checks and lightweight monitoring, r/homelab comments on topology freshness, r/networking reports of incorrect automated wiring maps, and historical Flashback requests for traffic visibility. See the pull request for linked examples.

## 2.0 workstreams

| Area | Existing implementation | Acceptance gate |
| --- | --- | --- |
| Topology | Local AP discovery and optional external AP descriptions | AP evidence tests, multi-interface regression, unknown paths not guessed, Ethernet-only behavior |
| Inventory | Identity sources, metadata, favorites, baseline, CSV/JSON export | Scalable rendering, search/filter/sort preserved, no user data discarded |
| Monitoring | Aggregate history, presence history, bounded port checks and webhook | Explicit not-seen vs offline, debounced alerts, opt-in configuration, retries |
| UI | Framework-free native ES modules, Swedish/English, mobile CSS | Phone/tablet/desktop tests, keyboard focus, accessible names, contrast and reduced motion |
| Performance | Local FastAPI, SQLite, no browser framework | Real ARM64 baseline and post-change CPU/RSS and request latency measurements |
| Security | Local-first, limited active probes | HTTP exposure and write-action review, no WAN scanning by default, no telemetry |
| Packaging | systemd/Docker with CI | Clean Ubuntu/Debian/ARM64 install, migration, rollback and container test |

## Implemented in first development slice

- Paginate device results after filtering and sorting, at most 50 rendered rows per page; full exports continue to include the inventory.
- Preserve the device search field on live polling; clamp pages if the list changes.
- Accessible pagination and Activity Center event controls, full timestamp names, selected-state and empty-state semantics.
- Focused tests and contributor guidance.

## 2.x backlog (not part of the 2.0.0 release)

- Optional authenticated collectors for evidence-based VLAN/switch/AP topology; never assume physical links from IP addresses.
- User-defined bounded service health checks and local alert routing, with allowlists and rate limits.
- Better device evidence explanations and multi-homed/private-MAC identity regression fixtures.
- Explicit privacy-preserving configuration backup/migration workflow.
- Reliable resource budget and performance profiling under hundreds of devices.

## Release validation checklist

1. All backend, frontend, browser, packaging and security CI tests must pass.
2. Physical Raspberry Pi ARM64 and clean Linux host testing (including Ethernet-only).
3. Measured memory, CPU, response time and mobile performance, compared against 1.6.x.
4. Upgrade/rollback and SQLite migration validation; documented user-visible changes.
5. Release notes, signed or traceable artifacts, container tags and compatibility docs verified before `project.json` changes to 2.0.0.

Avoid mandatory SNMP credentials, extra database containers, inaccurate traffic-rate claims without counter sources, aggressive subnet scans and optional cloud dependencies in the core.
