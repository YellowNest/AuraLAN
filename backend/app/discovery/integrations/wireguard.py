from __future__ import annotations

from typing import Any

from ..command import command_exists, run_command


def parse_wg_dump(output: str) -> tuple[int, int]:
    interfaces: set[str] = set()
    peers = 0
    for line in output.splitlines():
        columns = line.split("\t")
        if len(columns) >= 5:
            interfaces.add(columns[0])
            if len(columns) >= 9:
                peers += 1
    return len(interfaces), peers


def discover(interface_rows: list[dict[str, Any]], containers: list[dict[str, Any]]) -> dict[str, Any]:
    kernel_interfaces = [row["name"] for row in interface_rows if row["type"] == "wireguard" or row["name"].startswith("wg")]
    wg_easy = next((row for row in containers if "wg-easy" in row["name"].lower() or "wg-easy" in row["image"].lower()), None)
    interfaces = len(kernel_interfaces)
    peers: int | None = None
    runtime = "kernel" if interfaces else None
    if command_exists("wg"):
        result = run_command(["wg", "show", "all", "dump"])
        if result.code == 0 and result.output:
            interfaces, peers = parse_wg_dump(result.output)
            runtime = "native" if interfaces else runtime
    detected = bool(interfaces or wg_easy)
    frontend = None
    if wg_easy:
        frontend = {"name": wg_easy["name"], "state": wg_easy["state"], "runtime": "docker"}
    online = bool(interfaces) or bool(wg_easy and wg_easy["state"] == "running")
    return {
        "id": "wireguard", "name": "WireGuard", "detected": detected, "state": "online" if online else "unknown",
        "runtime": runtime or ("docker" if wg_easy else None),
        "summary": f"{interfaces} interface{'s' if interfaces != 1 else ''}" if interfaces else ("VPN frontend detected" if wg_easy else "Not detected"),
        "importance": "optional",
        "details": {"interfaces": kernel_interfaces, "peer_count": peers, "frontend": frontend},
    }
