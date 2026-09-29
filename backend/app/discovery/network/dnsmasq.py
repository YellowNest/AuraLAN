from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..command import command_exists, run_command

DEFAULT_LEASE_FILE = Path("/var/lib/misc/dnsmasq.leases")


def _service_rows() -> list[dict[str, str]]:
    if not command_exists("systemctl"):
        return []
    result = run_command(
        ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "dnsmasq*.service"]
    )
    if result.code != 0:
        return []
    rows = []
    for line in result.output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].startswith("dnsmasq"):
            rows.append({"unit": parts[0], "active": parts[2]})
    return rows


def _config_path(unit: str) -> Path | None:
    result = run_command(["systemctl", "show", unit, "-p", "ExecStart", "--value"])
    if result.code != 0:
        return None
    match = re.search(r"--conf-file=(\S+)", result.output)
    return Path(match.group(1)) if match else None


def _config_values(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"interface", "dhcp-leasefile"}:
            values[key] = value.strip()
    return values


def leases(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines:
        fields = line.split()
        if len(fields) < 4:
            continue
        expiry, mac, ip, hostname = fields[:4]
        try:
            expires_at = int(expiry)
        except ValueError:
            expires_at = None
        entries.append(
            {
                "mac": mac.upper(),
                "ip": ip,
                "hostname": None if hostname == "*" else hostname,
                "lease_expires_at": expires_at,
            }
        )
    return entries


def discover(access_point_interface: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Find the active dnsmasq belonging to the AP, never a generic resolver blindly."""
    candidates = _service_rows()
    selected: dict[str, Any] | None = None
    for row in candidates:
        config = _config_values(_config_path(row["unit"]))
        if access_point_interface and config.get("interface") == access_point_interface:
            selected = {**row, **config}
            break
        if selected is None and row["active"] == "active":
            selected = {**row, **config}
    if not selected:
        return ({"detected": False, "state": "unknown", "unit": None, "interface": access_point_interface, "lease_count": 0}, [])
    lease_file = Path(selected.get("dhcp-leasefile") or DEFAULT_LEASE_FILE)
    lease_entries = leases(lease_file)
    return (
        {
            "detected": True,
            "state": "online" if selected.get("active") == "active" else "offline",
            "unit": selected["unit"],
            "interface": selected.get("interface") or access_point_interface,
            "lease_count": len(lease_entries),
        },
        lease_entries,
    )
