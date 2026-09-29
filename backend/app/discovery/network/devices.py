"""Merge passive device observations into conservative, browser-safe identities."""

from __future__ import annotations

import concurrent.futures
import os
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from ..device_discovery import DeviceObservation
from ..device_discovery import dhcp, dns_sd, local_names, mdns, neigh, netbios, pihole_network, resolver, ssdp, wifi
from ..device_inference import clean_hostname, device_icon_key, friendly_description, infer_device_type
from ...persistence.device_store import DeviceStore, store

ACTIVE_NEIGHBOUR_STATES = {"REACHABLE", "DELAY", "PROBE"}
RECENT_NEIGHBOUR_STATES = {"STALE"}
CATEGORIES = {
    "phone", "tablet", "computer", "tv", "media_player", "speaker", "smart_home", "iot", "camera", "printer",
    "router", "access_point", "server", "raspberry_pi", "microcontroller", "console", "watch", "unknown",
}


def neighbours() -> list[dict[str, str]]:
    """Compatibility helper for diagnostics and parser tests."""
    return neigh.rows()


def _connection_type(evidence: Iterable[DeviceObservation]) -> str:
    """Describe the client's medium only when AuraLAN has direct evidence.

    Seeing a client through the Pi's Ethernet uplink does *not* mean the client
    itself is wired; it may be on Wi-Fi behind the router/AP.
    """
    items = tuple(evidence)
    if any(item.source == "wifi_station" for item in items):
        return "wifi"
    if any(item.role == "access_point" for item in items):
        return "wifi"
    if any(item.role == "vpn" for item in items):
        return "vpn"
    return "unknown"


def _normalise_mac(mac: str) -> str:
    return mac.upper().replace("-", ":")


def mac_type(mac: str) -> str:
    try:
        first = int(mac.split(":", 1)[0], 16)
    except (ValueError, IndexError):
        return "unknown"
    return "private" if first & 0x02 else "global"


def _merge_system_oui(prefixes: dict[str, str], path: Path) -> None:
    """Merge common Linux OUI databases when the host already has one installed."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return

    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        ieee = re.match(r"^([0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){2})\s+\(hex\)\s+(.+)$", value)
        compact = re.match(r"^([0-9A-Fa-f]{6,9})\s+(.+)$", value)
        if ieee:
            prefix = re.sub(r"[^0-9A-Fa-f]", "", ieee.group(1)).upper()
            vendor = ieee.group(2).strip()
        elif compact:
            prefix = compact.group(1).upper()
            vendor = compact.group(2).strip()
        else:
            continue
        if len(prefix) in {6, 7, 9} and vendor:
            prefixes.setdefault(prefix, vendor)


@lru_cache(maxsize=1)
def _oui_prefixes() -> dict[str, str]:
    """Load standard offline host OUI registries, optionally with one explicit override."""
    prefixes: dict[str, str] = {}
    configured = os.environ.get("AURALAN_OUI_FILE", "").strip()
    candidates = (
        *([Path(configured)] if configured else []),
        Path("/usr/share/ieee-data/oui.txt"),
        Path("/var/lib/ieee-data/oui.txt"),
        Path("/usr/share/misc/oui.txt"),
        Path("/usr/share/nmap/nmap-mac-prefixes"),
        Path("/usr/share/arp-scan/ieee-oui.txt"),
    )
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        _merge_system_oui(prefixes, candidate)
    return prefixes


def oui_vendor(mac: str) -> str | None:
    """Return the most-specific offline IEEE organization for a global MAC."""
    if mac_type(mac) != "global":
        return None
    normalized = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
    prefixes = _oui_prefixes()
    for length in (9, 7, 6):  # MA-S (/36), MA-M (/28), then MA-L/OUI (/24).
        vendor = prefixes.get(normalized[:length])
        if vendor:
            return vendor
    return None


def friendly_vendor(vendor: str | None) -> str | None:
    """Use a compact organization label in the human view; retain the registry value in identity."""
    if not vendor:
        return None
    known = {
        "Apple, Inc.": "Apple", "Espressif Inc.": "Espressif", "Raspberry Pi Foundation": "Raspberry Pi",
        "Raspberry Pi Trading Ltd": "Raspberry Pi", "Zyxel Communications Corporation": "Zyxel",
        "Chengdu Meross Technology Co., Ltd.": "Meross", "Beijing Roborock Technology Co., Ltd.": "Roborock",
        "Meta Platforms, Inc.": "Meta", "Liteon Technology Corporation": "Liteon", "Intel Corporate": "Intel",
        "Google, Inc.": "Google",
    }
    if vendor in known:
        return known[vendor]
    compact = re.sub(r",?\s+(?:Incorporated|Corporation|Corp\.?|Limited|Ltd\.?|LLC|Inc\.?)$", "", vendor, flags=re.IGNORECASE)
    return compact.strip() or vendor


def _field(value: str | None, source: str, confidence: str) -> dict[str, str] | None:
    return {"value": value, "source": source, "confidence": confidence} if value else None


def _product_vendor(*values: str | None) -> str | None:
    corpus = " ".join(value for value in values if value).lower()
    if re.search(r"\biphone\b|\bipad\b|\bmacbook\b|\bimac\b|\bapple\s*tv\b|\bhomepod\b|\biphone\d|\bipad\d|\bmacbook(?:pro|air)?\d|\bappletv\d|\baudioaccessory\d|_mediaremotetv\._tcp|_appletv-v2\._tcp|_apple-mobdev2\._tcp", corpus):
        return "Apple"
    if re.search(r"\bpixel\b|\bchromecast\b|\bnest\b", corpus):
        return "Google"
    if re.search(r"\bgalaxy\b|\bsm-[a-z0-9]+\b", corpus):
        return "Samsung"
    return None


def _fallback_name(vendor: str | None, category: str) -> str:
    short_vendor = friendly_vendor(vendor)
    if short_vendor == "Espressif":
        return "ESP device"
    if short_vendor == "Raspberry Pi":
        return "Raspberry Pi"
    device_type = friendly_description(category)
    if short_vendor and category != "unknown":
        return f"{short_vendor} {device_type}"
    if short_vendor:
        return f"{short_vendor} device"
    if category != "unknown":
        return device_type
    return "Network device"


def _clean_service_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    # Some Apple TV Bonjour names arrive localized as "Apple de TV".
    # Normalize only this product-family phrase; manual aliases are untouched.
    cleaned = re.sub(r"\bApple\s+de\s+TV\b", "Apple TV", cleaned, flags=re.IGNORECASE)
    if not cleaned or len(cleaned) > 80:
        return None
    if re.fullmatch(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", cleaned):
        return None
    if re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", cleaned):
        return None
    return cleaned


def _model_display(model: str | None, vendor: str | None) -> str | None:
    cleaned_model = _clean_service_name(model)
    if not cleaned_model:
        return None

    # Bonjour often advertises exact Apple hardware identifiers. Keep the raw
    # identifier in the model field, but use the familiar product family as
    # the primary fallback name when no user/device name exists.
    family_patterns = (
        (r"^iphone\d", "iPhone"),
        (r"^ipad\d", "iPad"),
        (r"^macbookpro\d", "MacBook Pro"),
        (r"^macbookair\d", "MacBook Air"),
        (r"^macbook\d", "MacBook"),
        (r"^imac\d", "iMac"),
        (r"^appletv\d", "Apple TV"),
        (r"^audioaccessory\d", "HomePod"),
    )
    lowered = cleaned_model.lower().replace(" ", "")
    for pattern, family in family_patterns:
        if re.search(pattern, lowered):
            return family

    short_vendor = friendly_vendor(vendor)
    if short_vendor and short_vendor.lower() not in cleaned_model.lower():
        return f"{short_vendor} {cleaned_model}"
    return cleaned_model


HOSTNAME_IDENTITY_SOURCES = {
    "dhcp_lease", "local_hosts", "mdns_name", "dns_sd", "pihole_network", "netbios_name", "local_resolver", "identity_cache",
}
MULTI_NIC_CATEGORIES = {"computer", "server", "printer"}
GENERIC_HOST_KEYS = {"pc", "computer", "desktop", "laptop", "server", "printer", "localhost", "unknown"}


def _hostname_identity_key(record: dict[str, Any]) -> str | None:
    hostname = str(record.get("hostname") or "").strip().lower()
    if not hostname:
        return None
    key = re.sub(r"[^a-z0-9]+", "", hostname)
    if len(key) < 4 or key in GENERIC_HOST_KEYS:
        return None
    sources = {str(item.get("source") or "") for item in (record.get("identity") or {}).get("sources", [])}
    display_source = str(((record.get("identity") or {}).get("display_name") or {}).get("source") or "")
    if not ((sources | {display_source}) & HOSTNAME_IDENTITY_SOURCES):
        return None
    return key


def _merge_device_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge records proven to share one trusted hostname across multiple NICs."""
    aliases = {str((item.get("metadata") or {}).get("alias") or "").strip() for item in records}
    aliases.discard("")
    overrides = {str((item.get("metadata") or {}).get("category_override") or "").strip() for item in records}
    overrides.discard("")
    notes = {str((item.get("metadata") or {}).get("note") or "").strip() for item in records}
    notes.discard("")
    locations = {str((item.get("metadata") or {}).get("location") or "").strip() for item in records}
    locations.discard("")
    tags = {
        tuple((item.get("metadata") or {}).get("tags") or [])
        for item in records
        if (item.get("metadata") or {}).get("tags")
    }
    if len(aliases) > 1 or len(overrides) > 1 or len(notes) > 1 or len(locations) > 1 or len(tags) > 1:
        # User-owned labels explicitly distinguish these records.
        return {}

    def score(item: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, int, int, str]:
        metadata = item.get("metadata") or {}
        return (
            1 if metadata.get("alias") else 0,
            1 if metadata.get("category_override") else 0,
            1 if metadata.get("note") else 0,
            1 if metadata.get("location") else 0,
            1 if metadata.get("tags") else 0,
            1 if metadata.get("favorite") else 0,
            1 if item.get("vendor") else 0,
            1 if item.get("model") else 0,
            1 if item.get("online") is True else 0,
            str(item.get("id") or ""),
        )

    ordered = sorted(records, key=score, reverse=True)
    primary = dict(ordered[0])
    macs = list(dict.fromkeys(
        str(value).upper()
        for item in ordered
        for value in (item.get("mac_addresses") or [item.get("mac")])
        if value
    ))
    ips = list(dict.fromkeys(
        str(value)
        for item in ordered
        for value in (item.get("ip_addresses") or [item.get("ip")])
        if value and value != "—"
    ))
    observations = []
    seen_observations: set[tuple[object, ...]] = set()
    for item in ordered:
        for observation in item.get("observations") or []:
            key = (
                observation.get("source"), observation.get("interface"),
                observation.get("ip"), observation.get("neighbor_state"),
            )
            if key not in seen_observations:
                seen_observations.add(key)
                observations.append(observation)

    primary["mac_addresses"] = macs
    primary["ip_addresses"] = ips
    if ips:
        primary["ip"] = ips[0]
    primary["observations"] = observations
    primary["dhcp"] = any(bool(item.get("dhcp")) for item in ordered)
    primary["online"] = True if any(item.get("online") is True for item in ordered) else primary.get("online")
    if primary["online"] is True:
        primary["state"] = "online"
    elif any(item.get("state") == "recently_seen" for item in ordered):
        primary["state"] = "recently_seen"
    first_seen = [item.get("first_seen_at") for item in ordered if item.get("first_seen_at") is not None]
    last_seen = [item.get("last_seen_at") for item in ordered if item.get("last_seen_at") is not None]
    if first_seen:
        primary["first_seen_at"] = min(first_seen)
    if last_seen:
        primary["last_seen_at"] = max(last_seen)

    primary_metadata = dict(primary.get("metadata") or {})
    if notes and not primary_metadata.get("note"):
        primary_metadata["note"] = next(iter(notes))
    if locations and not primary_metadata.get("location"):
        primary_metadata["location"] = next(iter(locations))
    if tags and not primary_metadata.get("tags"):
        primary_metadata["tags"] = list(next(iter(tags)))
    primary_metadata["favorite"] = any(bool((item.get("metadata") or {}).get("favorite")) for item in ordered)
    primary["metadata"] = primary_metadata

    # Preserve the strongest available vendor/model/identity while keeping the
    # display name/hostname that proved these interfaces belong together.
    for field in ("vendor", "model"):
        if not primary.get(field):
            primary[field] = next((item.get(field) for item in ordered if item.get(field)), None)
    return primary


def _coalesce_physical_devices(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []
    for record in records:
        hostname_key = _hostname_identity_key(record)
        if record.get("category") not in MULTI_NIC_CATEGORIES or not hostname_key:
            passthrough.append(record)
            continue
        groups.setdefault(hostname_key, []).append(record)

    for grouped in groups.values():
        if len(grouped) == 1:
            passthrough.extend(grouped)
            continue
        merged = _merge_device_records(grouped)
        if merged:
            passthrough.append(merged)
        else:
            passthrough.extend(grouped)
    return passthrough


def resolve_observations(
    observations: Iterable[DeviceObservation],
    metadata: dict[str, dict[str, Any]] | None = None,
    *,
    coalesce: bool = True,
) -> list[dict[str, Any]]:
    """Resolve MAC identities and conservatively collapse proven multi-NIC hosts."""
    groups: dict[str, list[DeviceObservation]] = {}
    for observation in observations:
        mac = _normalise_mac(observation.mac)
        if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
            continue
        groups.setdefault(mac, []).append(observation)
    metadata = metadata or {}
    records: list[dict[str, Any]] = []
    for mac, evidence in groups.items():
        identifier = mac.lower().replace(":", "")
        manual = metadata.get(identifier, {})
        cached_identity = manual.get("cached_identity") or {}
        hostname_observation = next((item for item in evidence if item.source == "dhcp_lease" and item.hostname), None)
        hostname_observation = hostname_observation or next((item for item in evidence if item.source == "local_hosts" and item.hostname), None)
        hostname_observation = hostname_observation or next((item for item in evidence if item.source == "mdns_name" and item.hostname), None)
        hostname_observation = hostname_observation or next((item for item in evidence if item.source == "dns_sd" and item.hostname), None)
        hostname_observation = hostname_observation or next((item for item in evidence if item.source == "pihole_network" and item.hostname), None)
        hostname_observation = hostname_observation or next((item for item in evidence if item.source == "netbios_name" and item.hostname), None)
        hostname_observation = hostname_observation or next((item for item in evidence if item.source == "local_resolver" and item.hostname), None)
        observed_hostname = hostname_observation.hostname if hostname_observation else cached_identity.get("hostname")
        hostname_source = hostname_observation.source if hostname_observation else ("identity_cache" if observed_hostname else None)
        cleaned_hostname = clean_hostname(observed_hostname)
        service_observation = next((item for item in evidence if item.source == "dns_sd" and item.service_name), None)
        service_observation = service_observation or next((item for item in evidence if item.source == "ssdp" and item.service_name), None)
        service_name = _clean_service_name(service_observation.service_name if service_observation else None)
        live_model_observation = next((item for item in evidence if item.source == "dns_sd" and item.model), None)
        live_model_observation = live_model_observation or next((item for item in evidence if item.source == "ssdp" and item.model), None)
        live_model = live_model_observation.model if live_model_observation else None
        advertised_model = live_model or cached_identity.get("model")
        model_source = live_model_observation.source if live_model_observation else ("identity_cache" if advertised_model else None)
        manufacturer_observation = next((item for item in evidence if item.source == "dns_sd" and item.manufacturer), None)
        manufacturer_observation = manufacturer_observation or next((item for item in evidence if item.source == "ssdp" and item.manufacturer), None)
        manufacturer_observation = manufacturer_observation or next((item for item in evidence if item.source == "pihole_network" and item.manufacturer), None)
        advertised_manufacturer = manufacturer_observation.manufacturer if manufacturer_observation else None
        service_hints = tuple(dict.fromkeys(
            hint
            for item in evidence
            for hint in (*item.service_types, item.service_name or "", item.model or "", item.manufacturer or "")
            if hint
        ))
        registry_vendor = oui_vendor(mac)
        product_vendor = _product_vendor(observed_hostname, service_name, advertised_model, *service_hints)
        cached_vendor = cached_identity.get("vendor")
        vendor_source = (
            "oui_vendor" if registry_vendor
            else manufacturer_observation.source if advertised_manufacturer and manufacturer_observation
            else "product_signature" if product_vendor
            else "identity_cache" if cached_vendor
            else None
        )
        raw_vendor = registry_vendor or advertised_manufacturer or product_vendor or cached_vendor
        vendor = friendly_vendor(raw_vendor)
        model_display = _model_display(advertised_model, raw_vendor)
        inferred = infer_device_type(
            hostname=" ".join(filter(None, (observed_hostname, service_name, advertised_model))),
            vendor=raw_vendor,
            service_hints=service_hints,
        )
        automatic_category, category_source, category_confidence = inferred.device_type, inferred.evidence, inferred.confidence
        cached_category = cached_identity.get("category")
        if automatic_category == "unknown" and cached_category in CATEGORIES and cached_category != "unknown":
            automatic_category, category_source, category_confidence = cached_category, "identity_cache", "medium"
        category_override = manual.get("category_override")
        category = category_override if category_override in CATEGORIES else automatic_category
        category_identity = _field(category, "manual_alias" if category_override else category_source, "high" if category_override else category_confidence)
        alias = manual.get("alias")
        icon_key = device_icon_key(
            category=category,
            vendor=raw_vendor,
            hostname=" ".join(filter(None, (observed_hostname, service_name, alias))),
            model=advertised_model,
            service_hints=service_hints,
        )
        if icon_key == "device_generic" and cached_identity.get("icon_key"):
            icon_key = cached_identity["icon_key"]
        if alias:
            display = _field(alias, "manual_alias", "high")
        elif hostname_source in {"dhcp_lease", "local_hosts"} and cleaned_hostname:
            display = _field(cleaned_hostname, hostname_source, "high")
        elif service_name:
            display = _field(service_name, service_observation.source if service_observation else "heuristic", "medium")
        elif model_display and model_source == "dns_sd":
            display = _field(model_display, "dns_sd", "medium")
        elif cleaned_hostname and hostname_source != "identity_cache":
            display = _field(cleaned_hostname, hostname_source or "heuristic", "medium")
        elif cached_identity.get("display_name"):
            display = _field(cached_identity["display_name"], "identity_cache", "medium")
        elif model_display:
            display = _field(model_display, "identity_cache", "medium")
        elif cleaned_hostname:
            display = _field(cleaned_hostname, "identity_cache", "medium")
        else:
            display = _field(_fallback_name(vendor, category), "heuristic", "low")
        neighbour_online = any(item.neighbour_state in ACTIVE_NEIGHBOUR_STATES for item in evidence)
        wifi_online = any(item.source == "wifi_station" for item in evidence)
        stale = any(item.neighbour_state in RECENT_NEIGHBOUR_STATES for item in evidence)
        failed = any(item.neighbour_state == "FAILED" for item in evidence)
        if wifi_online or neighbour_online:
            online, state = True, "online"
        elif failed:
            online, state = False, "offline"
        elif stale or any(item.source == "dhcp_lease" for item in evidence):
            online, state = None, "recently_seen"
        else:
            online, state = None, "unknown"
        preferred = sorted(evidence, key=lambda item: (
            item.source == "wifi_station", item.neighbour_state in ACTIVE_NEIGHBOUR_STATES,
            item.role in {"access_point", "uplink"}, item.source == "dhcp_lease",
        ), reverse=True)[0]
        ips = list(dict.fromkeys(item.ip for item in evidence if item.ip))
        signal = next((item.signal_dbm for item in evidence if item.signal_dbm is not None), None)
        lease = next((item for item in evidence if item.source == "dhcp_lease"), None)
        sources = []
        for source in sorted({item.source for item in evidence}):
            confidence = "high" if source in {"dhcp_lease", "wifi_station", "local_hosts"} else "medium"
            sources.append({"source": source, "confidence": confidence})
        if registry_vendor:
            sources.append({"source": "oui_vendor", "confidence": "high"})
        if cached_identity and not any(source["source"] == "identity_cache" for source in sources):
            sources.append({"source": "identity_cache", "confidence": "medium"})
        if alias or category_override:
            sources.append({"source": "manual_alias", "confidence": "high"})
        records.append({
            "id": identifier,
            "display_name": display["value"], "hostname": observed_hostname,
            "vendor": vendor, "model": _clean_service_name(advertised_model), "device_type": category, "category": category, "icon_key": icon_key,
            "ip": ips[0] if ips else "—", "ip_addresses": ips, "mac": mac, "mac_addresses": [mac], "mac_type": mac_type(mac),
            "interface": preferred.interface, "connection_type": _connection_type(evidence),
            "online": online, "state": state, "signal_dbm": signal,
            "signal_quality": signal_quality(signal), "dhcp": lease is not None,
            "lease_expires_at": lease.lease_expires_at if lease else None,
            "lease": {"present": lease is not None, "expires_at": lease.lease_expires_at if lease else None},
            "first_seen_at": manual.get("first_seen_at"), "last_seen_at": manual.get("last_seen_at"),
            "identity": {
                "display_name": display,
                "vendor": _field(raw_vendor, vendor_source or "heuristic", "high" if registry_vendor else "medium") if raw_vendor else None,
                "model": _field(advertised_model, model_source or "heuristic", "medium") if advertised_model else None,
                "device_type": category_identity,
                "sources": sources,
            },
            "metadata": {
                "alias": alias,
                "category_override": category_override,
                "note": manual.get("note"),
                "favorite": bool(manual.get("favorite")),
                "location": manual.get("location"),
                "tags": list(manual.get("tags") or []),
            },
            "observations": [
                {"source": item.source, "interface": item.interface, "ip": item.ip, "neighbor_state": item.neighbour_state}
                for item in evidence
            ],
        })
    if coalesce:
        records = _coalesce_physical_devices(records)
    return sorted(records, key=lambda item: (
        item["online"] is not True,
        item["state"] != "recently_seen",
        item["identity"]["display_name"]["confidence"] == "low",
        item["display_name"].lower(),
        item["ip"],
    ))


def signal_quality(signal_dbm: int | None) -> str | None:
    if signal_dbm is None:
        return None
    if signal_dbm >= -55:
        return "excellent"
    if signal_dbm >= -67:
        return "good"
    if signal_dbm >= -75:
        return "fair"
    return "weak"


def collect_devices(interface_rows: list[dict[str, Any]], lease_entries: list[dict[str, Any]], signals: dict[str, int], device_store: DeviceStore | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect isolated passive providers, merge them, and return human diagnostics."""
    roles = {row["name"]: row["role"] for row in interface_rows}
    access_point = next((name for name, role in roles.items() if role == "access_point"), None)
    provider_results: list[DeviceObservation] = []
    warnings: list[str] = []
    for provider_name, provider in (
        ("neighbour table", lambda: neigh.observations(roles)),
        ("DHCP leases", lambda: dhcp.observations(lease_entries, access_point)),
        ("Wi-Fi stations", lambda: wifi.observations(signals, access_point)),
    ):
        try:
            provider_results.extend(provider())
        except Exception as exc:
            warnings.append(f"Could not read {provider_name}: {type(exc).__name__}")
    enrichment_seed = list(provider_results)
    enrichers = {
        "local mDNS names": lambda: mdns.observations(enrichment_seed),
        "local host names": lambda: local_names.observations(enrichment_seed),
        "local DNS-SD services": lambda: dns_sd.observations(enrichment_seed),
        "configured resolver names": lambda: resolver.observations(enrichment_seed),
        "NetBIOS names": lambda: netbios.observations(enrichment_seed),
        "SSDP/UPnP friendly names": lambda: ssdp.observations(enrichment_seed),
        "Pi-hole network identity": lambda: pihole_network.observations(enrichment_seed),
    }
    # These sources are independent and individually bounded. Running them
    # together keeps first-load identity enrichment inside one short latency
    # window rather than stacking DNS/mDNS timeouts serially.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(enrichers), thread_name_prefix="auralan-identity") as executor:
        futures = {executor.submit(provider): name for name, provider in enrichers.items()}
        for future in concurrent.futures.as_completed(futures):
            provider_name = futures[future]
            try:
                provider_results.extend(future.result())
            except Exception as exc:
                warnings.append(f"Could not read {provider_name}: {type(exc).__name__}")
    preliminary = resolve_observations(provider_results, coalesce=False)
    active_store = device_store or store()
    try:
        active_store.remember_identities(preliminary)
        metadata = active_store.enrich([item["id"] for item in preliminary])
    except (OSError, sqlite3.Error) as exc:
        metadata = {}
        warnings.append(f"AuraLAN device metadata storage is unavailable: {type(exc).__name__}")
    new_ids = {identifier for identifier, item in metadata.items() if item.get("_new_presence")}
    resolved = resolve_observations(provider_results, metadata)
    try:
        active_store.remember_identities(resolved)
        active_store.remember_inventory(resolved)
        active_store.record_first_seen(resolved, new_ids)
    except (OSError, sqlite3.Error):
        pass
    return resolved, warnings


def build_devices(interface_rows: list[dict[str, Any]], lease_entries: list[dict[str, Any]], signals: dict[str, int], device_store: DeviceStore | None = None) -> list[dict[str, Any]]:
    """Compatibility convenience wrapper for callers that need only records."""
    return collect_devices(interface_rows, lease_entries, signals, device_store)[0]
