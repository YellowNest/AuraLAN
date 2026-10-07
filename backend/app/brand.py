"""Runtime brand metadata, kept independent from legacy service names."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BRAND_FILE = ROOT / "project.json"

DEFAULT_BRAND: dict[str, Any] = {
    "productName": "AuraLAN",
    "shortName": "AuraLAN",
    "tagline": "Your network, clearly.",
    "version": "1.6.0",
    "apiVersion": "v1",
    "repository": {"url": "", "issues": ""},
    "accent": {"primary": "#3B82F6", "soft": "#EAF2FF"},
}


def brand() -> dict[str, Any]:
    """Read the single distributable source of product metadata safely."""
    try:
        loaded = json.loads(BRAND_FILE.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return DEFAULT_BRAND.copy()
        return {**DEFAULT_BRAND, **loaded}
    except (OSError, ValueError):
        return DEFAULT_BRAND.copy()
