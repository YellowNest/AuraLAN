from __future__ import annotations

from typing import Any

from ..command import command_exists, run_command


WIFI_TYPES = {"802-11-wireless", "wifi"}


def _terse_fields(line: str) -> list[str]:
    """Split nmcli terse output while honoring its backslash escaping."""
    fields: list[list[str]] = [[]]
    escaped = False
    for character in line:
        if escaped:
            fields[-1].append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append([])
        else:
            fields[-1].append(character)
    if escaped:
        fields[-1].append("\\")
    return ["".join(field) for field in fields]


def active_connections() -> list[dict[str, str]]:
    if not command_exists("nmcli"):
        return []
    result = run_command(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE,STATE", "connection", "show", "--active"])
    if result.code != 0:
        return []
    rows: list[dict[str, str]] = []
    for line in result.output.splitlines():
        fields = _terse_fields(line)
        if len(fields) == 4:
            rows.append({"name": fields[0], "type": fields[1], "device": fields[2], "state": fields[3]})
    return rows


def active_wifi_connections() -> list[dict[str, str]]:
    """Return every active NetworkManager Wi-Fi connection, not just the first one."""
    return [row for row in active_connections() if row["type"] in WIFI_TYPES and row.get("device")]


def active_wifi() -> dict[str, str] | None:
    """Compatibility helper for callers that only need the first active Wi-Fi row."""
    return next(iter(active_wifi_connections()), None)


def connection_details(name: str) -> dict[str, str]:
    if not command_exists("nmcli"):
        return {}
    result = run_command(["nmcli", "-t", "-f", "802-11-wireless.ssid,802-11-wireless.channel", "connection", "show", name])
    if result.code != 0:
        return {}
    values: dict[str, str] = {}
    for line in result.output.splitlines():
        fields = _terse_fields(line)
        if len(fields) < 2:
            continue
        key = fields[0]
        value = ":".join(fields[1:])
        values[key.rsplit(".", 1)[-1]] = value
    return values


def wifi_candidates(preferred_interface: str | None = None) -> list[dict[str, Any]]:
    """Return active Wi-Fi candidates with optional interface preference.

    NetworkManager reports connection state; iw proves whether an interface is
    actually operating as an access point.
    """
    rows = active_wifi_connections()
    if preferred_interface:
        rows.sort(key=lambda row: row.get("device") != preferred_interface)

    candidates: list[dict[str, Any]] = []
    for row in rows:
        details = connection_details(row["name"])
        channel = details.get("channel")
        candidates.append({
            "connection": row["name"],
            "interface": row["device"],
            "ssid": details.get("ssid") or None,
            "channel": int(channel) if channel and channel.isdigit() else None,
        })
    return candidates


def network_manager_access_point() -> dict[str, Any]:
    """Compatibility shape; AP mode must still be confirmed with iw."""
    candidates = wifi_candidates()
    return {"available": False} if not candidates else {"available": True, **candidates[0]}
