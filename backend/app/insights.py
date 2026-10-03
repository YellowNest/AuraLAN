"""Aggregate local Network Pulse insights without exposing device identity."""

from __future__ import annotations

from typing import Any

DAY_SECONDS = 24 * 60 * 60


def _identity_score(device: dict[str, Any]) -> int:
    identity = device.get("identity") or {}
    display = identity.get("display_name") or {}
    metadata = device.get("metadata") or {}

    score = 0
    if metadata.get("alias"):
        score += 60
    elif display.get("confidence") == "high":
        score += 35
    elif display.get("confidence") == "medium":
        score += 25
    elif display.get("confidence") == "low":
        score += 5

    if device.get("vendor") or (identity.get("vendor") or {}).get("value"):
        score += 20
    if device.get("model") or (identity.get("model") or {}).get("value"):
        score += 20

    category = device.get("category") or device.get("device_type") or "unknown"
    if category != "unknown":
        score += 20
        confidence = (identity.get("device_type") or {}).get("confidence")
        if confidence == "high":
            score += 15
        elif confidence == "medium":
            score += 8

    if device.get("hostname"):
        score += 10

    source_confidence = {
        item.get("confidence")
        for item in (identity.get("sources") or [])
        if isinstance(item, dict)
    }
    if "high" in source_confidence:
        score += 10
    elif "medium" in source_confidence:
        score += 5

    return max(0, min(score, 100))


def build_network_insights(
    snapshot: dict[str, Any],
    baseline: dict[str, Any],
    activity_24h: dict[str, int],
    activity_7d: dict[str, int],
    activity_days: list[dict[str, int]],
    *,
    now: int,
) -> dict[str, Any]:
    """Build privacy-preserving aggregate network insight counts."""

    devices = list(snapshot.get("devices") or [])
    services = [
        item for item in (snapshot.get("services") or {}).get("items", [])
        if item.get("detected")
    ]

    current_devices = [item for item in devices if item.get("state") != "known"]
    remembered_devices = [item for item in devices if item.get("state") == "known"]
    favorites = [
        item for item in devices
        if bool((item.get("metadata") or {}).get("favorite"))
    ]
    favorites_not_seen = [
        item for item in favorites
        if item.get("state") == "known"
    ]

    identity_needs_review = sum(
        1 for item in devices
        if _identity_score(item) < 40
    )
    new_devices_24h = sum(
        1
        for item in devices
        if isinstance(item.get("first_seen_at"), int)
        and 0 <= now - int(item["first_seen_at"]) <= DAY_SECONDS
    )
    services_offline = sum(1 for item in services if item.get("state") == "offline")
    discovery_errors = len(snapshot.get("errors") or [])
    baseline_new = int(baseline.get("new_count") or 0)
    baseline_missing = int(baseline.get("missing_count") or 0)

    attention_count = (
        len(favorites_not_seen)
        + services_offline
        + baseline_missing
        + discovery_errors
    )
    changed_count = (
        baseline_new
        + new_devices_24h
        + int(activity_24h.get("service_changes") or 0)
    )

    if attention_count:
        state = "attention"
    elif changed_count or int(activity_24h.get("total") or 0):
        state = "changed"
    else:
        state = "quiet"

    return {
        "state": state,
        "attention_count": attention_count,
        "current_devices": len(current_devices),
        "remembered_devices": len(remembered_devices),
        "online_devices": sum(1 for item in devices if item.get("online") is True),
        "identity_needs_review": identity_needs_review,
        "favorites_total": len(favorites),
        "favorites_not_seen_now": len(favorites_not_seen),
        "new_devices_24h": new_devices_24h,
        "baseline_new": baseline_new,
        "baseline_missing": baseline_missing,
        "services_detected": len(services),
        "services_offline": services_offline,
        "discovery_errors": discovery_errors,
        "activity_24h": activity_24h,
        "activity_7d": activity_7d,
        "activity_days": activity_days,
    }
