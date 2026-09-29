from __future__ import annotations

import re
from typing import Any

from ..command import command_exists, run_command


def parse_iw_info(output: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    type_match = re.search(r"^\s*type\s+(\S+)", output, re.MULTILINE)
    ssid_match = re.search(r"^\s*ssid\s+(.+)$", output, re.MULTILINE)
    channel_match = re.search(r"channel\s+(\d+)\s+\((\d+)\s+MHz\)", output)
    if type_match:
        info["type"] = type_match.group(1).upper()
    if ssid_match:
        info["ssid"] = ssid_match.group(1).strip()
    if channel_match:
        info["channel"] = int(channel_match.group(1))
        info["frequency_mhz"] = int(channel_match.group(2))
        info["band"] = "2.4 GHz" if info["frequency_mhz"] < 3000 else ("5 GHz" if info["frequency_mhz"] < 5925 else "6 GHz")
    return info


def parse_iw_dev(output: str) -> list[dict[str, str]]:
    """Parse iw dev without assuming a conventional wireless interface name."""
    rows: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in output.splitlines():
        interface = re.match(r"^\s*Interface\s+(\S+)", line)
        if interface:
            current = {"name": interface.group(1)}
            rows.append(current)
            continue
        kind = re.match(r"^\s*type\s+(\S+)", line)
        if kind and current is not None:
            current["type"] = kind.group(1).upper()
    return rows


def wireless_interfaces() -> list[dict[str, str]]:
    if not command_exists("iw"):
        return []
    result = run_command(["iw", "dev"])
    return parse_iw_dev(result.output) if result.code == 0 else []


def interface_info(interface: str | None) -> dict[str, Any]:
    if not interface or not command_exists("iw"):
        return {}
    result = run_command(["iw", "dev", interface, "info"])
    return parse_iw_info(result.output) if result.code == 0 else {}


def station_signals(interface: str | None) -> dict[str, int]:
    if not interface or not command_exists("iw"):
        return {}
    result = run_command(["iw", "dev", interface, "station", "dump"])
    if result.code != 0:
        return {}
    signals: dict[str, int] = {}
    current_mac: str | None = None
    for line in result.output.splitlines():
        station = re.match(r"^Station\s+([0-9a-f:]{17})", line, re.IGNORECASE)
        signal = re.match(r"^\s*signal:\s*(-?\d+)", line)
        if station:
            current_mac = station.group(1).upper()
        elif signal and current_mac:
            signals[current_mac] = int(signal.group(1))
    return signals
