# Security

AuraLAN is designed to inspect local network state without sending device or network data to external services.

## Repository hygiene

Never commit:

- passwords, tokens, API keys, cookies, or authorization headers
- WireGuard/private VPN keys
- TLS private keys or certificates containing private material
- real `.env` files
- runtime SQLite databases or device metadata
- packet captures, HAR files, logs, or diagnostic bundles containing local data
- production configuration containing credentials

Use generic example values and documentation-only addresses in tests and examples. Prefer RFC 5737 ranges such as `192.0.2.0/24`, `198.51.100.0/24`, and `203.0.113.0/24`. Do not copy hostnames, MAC addresses, paths, or private LAN addresses from a live installation.

## Device privacy

Tests and documentation must not contain real household device names, personal names, production MAC addresses, or identifiers copied from a live installation.

Runtime discovery remains local. Device identity information must not be sent to third-party lookup APIs.

## Reporting a vulnerability

Do not open a public issue containing credentials, private network data, exploit details, or unredacted diagnostics. Use GitHub's private vulnerability reporting when it is available for the repository. If that option is unavailable, contact the repository owner through GitHub before sharing sensitive details.

AuraLAN has no cloud control plane or account system; security reports should identify the affected AuraLAN version, deployment mode, and whether the service was exposed beyond loopback.

## Before public release

Before changing the repository from private to public:

1. scan the full Git history, not only the current tree;
2. remove or rewrite any historical personal names, SSIDs, MAC addresses, credentials, or local diagnostic data;
3. verify example configuration contains only generic/documentation values;
4. review bundled vendor/OUI data and its license/provenance;
5. verify no generated runtime database or logs are tracked.

If a secret is ever committed, rotate the secret first. Removing it from the latest commit is not sufficient because Git history retains prior versions.
