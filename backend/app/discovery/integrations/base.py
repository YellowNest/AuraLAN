"""Shared metadata contract for modular integrations.

Providers only report safe runtime facts.  This registry supplies the human
description and declared capability surface used by API clients.
"""

from __future__ import annotations

from typing import Any


INTEGRATION_METADATA: dict[str, dict[str, Any]] = {
    "docker": {"category": "runtime", "description_key": "serviceDocker", "short_description": "Runs isolated applications", "capabilities": {"read_status": True, "read_clients": False, "read_config": False, "restart": False, "write_config": False}},
    "pihole": {"category": "dns", "description_key": "servicePihole", "short_description": "Blocks unwanted DNS requests", "capabilities": {"read_status": True, "read_clients": False, "read_config": False, "restart": False, "write_config": False}},
    "wireguard": {"category": "vpn", "description_key": "serviceWireguard", "short_description": "Provides secure remote network access", "capabilities": {"read_status": True, "read_clients": True, "read_config": False, "restart": False, "write_config": False}},
    "caddy": {"category": "proxy", "description_key": "serviceCaddy", "short_description": "Routes web traffic to local services", "capabilities": {"read_status": True, "read_clients": False, "read_config": False, "restart": False, "write_config": False}},
}

APP_CAPABILITIES = {
    "device_aliases": True,
    "device_category_overrides": True,
    "device_notes": True,
    "device_favorites": True,
    "device_locations": True,
    "device_tags": True,
    "device_presence": True,
    "device_presence_history": True,
    "background_monitor": True,
    "webhook_notifications": True,
    "home_assistant_summary": True,
    "wake_on_lan": False,
    "dhcp_editing": False,
    "wifi_editing": False,
    "service_actions": False,
}


def enrich(item: dict[str, Any]) -> dict[str, Any]:
    metadata = INTEGRATION_METADATA.get(item.get("id"), {})
    return {**item, "category": metadata.get("category", "other"), "description_key": metadata.get("description_key"), "short_description": metadata.get("short_description", item.get("summary", "")), "capabilities": metadata.get("capabilities", {"read_status": True})}
