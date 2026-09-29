#!/usr/bin/env python3
"""Run one fresh local AuraLAN discovery pass and print how devices were identified."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def field(value: object, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text or fallback


with tempfile.TemporaryDirectory(prefix="auralan-audit-") as state_dir:
    os.environ["AURALAN_DATA_DIR"] = state_dir

    from app.services.system import system_snapshot  # noqa: E402

    snapshot = system_snapshot(force=True)

network = snapshot.get("network") or {}
ap = network.get("access_point") or {}
devices = snapshot.get("devices") or []
errors = snapshot.get("errors") or []

print("AuraLAN local discovery audit")
print("=============================")
print(f"Host:        {field((snapshot.get('host') or {}).get('name'))}")
print(f"AP detected: {'yes' if ap.get('available') else 'no'}")
print(f"AP interface:{' ' + field(ap.get('interface'))}")
print(f"SSID:        {field(ap.get('ssid'))}")
print(f"Devices:     {len(devices)}")
print(f"Errors:      {len(errors)}")
print()

identified = 0
generic = 0

for index, device in enumerate(devices, 1):
    identity = device.get("identity") or {}
    display_identity = identity.get("display_name") or {}
    sources = []
    for item in identity.get("sources") or []:
        source = str(item.get("source") or "").strip()
        if source and source not in sources:
            sources.append(source)

    is_generic = (
        device.get("category") == "unknown"
        and not device.get("vendor")
        and str(display_identity.get("confidence") or "") == "low"
    )
    generic += int(is_generic)
    identified += int(not is_generic)

    print(f"[{index:02d}] {field(device.get('display_name'))}")
    print(
        "     "
        f"category={field(device.get('category'))}  "
        f"vendor={field(device.get('vendor'))}  "
        f"model={field(device.get('model'))}"
    )
    print(
        "     "
        f"state={field(device.get('state'))}  "
        f"connection={field(device.get('connection_type'))}  "
        f"icon={field(device.get('icon_key'))}"
    )
    print(
        "     "
        f"ip={field(device.get('ip'))}  "
        f"mac={field(device.get('mac'))}  "
        f"mac_type={field(device.get('mac_type'))}"
    )
    print(
        "     "
        f"name_source={field(display_identity.get('source'))}  "
        f"confidence={field(display_identity.get('confidence'))}  "
        f"sources={','.join(sources) if sources else '—'}"
    )
    print()

print("Summary")
print("-------")
print(f"Identified/non-generic: {identified}")
print(f"Generic/needs review:   {generic}")
if errors:
    print()
    print("Discovery warnings")
    print("------------------")
    for error in errors:
        print(f"- {error}")
