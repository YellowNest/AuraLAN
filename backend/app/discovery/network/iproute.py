from __future__ import annotations

import json
from typing import Any

from ..command import command_exists, run_command


def classify_interface(name: str, kind: str, access_point: str | None, uplink: str | None) -> str:
    """Give interfaces a conservative presentation role without changing them."""
    if name == access_point:
        return "access_point"
    if name == uplink:
        return "uplink"
    lower = name.lower()
    if kind == "wireguard" or lower.startswith(("wg", "tun", "tap")) or lower in {"sidestore"}:
        return "vpn"
    if lower == "docker0" or lower.startswith("br-"):
        return "container_bridge"
    # macvlan/ipvlan peers (for example a Hue emulator) are local infrastructure,
    # not independently connected clients.  Keep them in Network diagnostics only.
    if lower == "lo" or lower.startswith(("veth", "virbr")) or kind in {"macvlan", "ipvlan", "vlan", "dummy"}:
        return "virtual"
    return "unknown"


def _json_command(args: list[str]) -> list[dict[str, Any]]:
    if not command_exists("ip"):
        return []
    result = run_command(["ip", "-j", *args])
    if result.code != 0 or not result.output:
        return []
    try:
        loaded = json.loads(result.output)
        return loaded if isinstance(loaded, list) else []
    except ValueError:
        return []


def routes() -> list[dict[str, Any]]:
    return _json_command(["route", "show"])


def default_route(route_rows: list[dict[str, Any]]) -> dict[str, str | None]:
    row = next((item for item in route_rows if item.get("dst") == "default"), {})
    return {"interface": row.get("dev"), "gateway": row.get("gateway")}


def interfaces(access_point: str | None, uplink: str | None) -> list[dict[str, Any]]:
    # `ip -d` exposes linkinfo (notably macvlan) which plain JSON omits.
    links = _json_command(["-d", "link", "show"])
    addresses = _json_command(["addr", "show"])
    address_by_name = {row.get("ifname"): row for row in addresses if row.get("ifname")}
    result: list[dict[str, Any]] = []
    for link in links:
        name = link.get("ifname")
        if not name:
            continue
        address_row = address_by_name.get(name, {})
        # iproute2 JSON calls this field `linkinfo`; tolerate the historical
        # spelling as well so macvlan/veth classification never leaks into clients.
        link_info = link.get("linkinfo") or link.get("link_info") or {}
        kind = link_info.get("info_kind") or link.get("link_type") or "unknown"
        ipv4 = [
            f"{item.get('local')}/{item.get('prefixlen')}"
            for item in address_row.get("addr_info", [])
            if item.get("family") == "inet" and item.get("local")
        ]
        result.append(
            {
                "name": name,
                "type": kind,
                "addresses": ipv4,
                "state": str(link.get("operstate") or "unknown").lower(),
                "mtu": link.get("mtu"),
                "role": classify_interface(name, kind, access_point, uplink),
            }
        )
    return sorted(result, key=lambda row: (row["role"] == "unknown", row["name"]))


def ipv4_for(interface_rows: list[dict[str, Any]], name: str | None) -> str | None:
    if not name:
        return None
    row = next((item for item in interface_rows if item["name"] == name), None)
    return row["addresses"][0] if row and row["addresses"] else None
