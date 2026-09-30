"""Conservative, testable presentation inference for passive device evidence.

Signatures are data-only rules: they can suggest a broad class, never a specific
hardware model.  The resolver records the winning rule and confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInference:
    device_type: str
    confidence: str
    evidence: str


@dataclass(frozen=True)
class DeviceSignature:
    identifier: str
    pattern: str
    device_type: str
    confidence: str


@dataclass(frozen=True)
class DeviceIconSignature:
    identifier: str
    pattern: str
    icon_key: str


# This small schema is intentionally declarative so community additions can be
# reviewed as data/signature changes, without introducing executable plugins.
SIGNATURES = (
    DeviceSignature("printer-service", r"_ipp\._tcp|_ipps\._tcp|_printer\._tcp|airprint", "printer", "high"),
    DeviceSignature("homekit-camera", r"homekit-(?:camera|video-doorbell)", "camera", "high"),
    DeviceSignature("homekit-router", r"homekit-router", "router", "high"),
    DeviceSignature("homekit-television", r"homekit-television", "tv", "high"),
    DeviceSignature("homekit-audio", r"homekit-audio-receiver", "media_player", "high"),
    DeviceSignature("homekit-accessory", r"homekit-(?:bridge|fan|garage-door|light|lock|outlet|switch|thermostat|sensor|security-system|door|window|window-covering|programmable-switch|air-purifier|heater|air-conditioner|humidifier|dehumidifier|sprinkler|faucet|shower-system)", "smart_home", "high"),
    DeviceSignature("matter-accessory", r"_matter(?:c|d)?\._(?:tcp|udp)|\bmatter\b", "smart_home", "high"),
    DeviceSignature("nas-platform", r"\bsynology\b|\bqnap\b|\btruenas\b|\basustor\b", "server", "high"),
    DeviceSignature("android-tv", r"android[\s._-]*tv|google[\s._-]*tv|nvidia[\s._-]*shield", "tv", "high"),
    DeviceSignature("phone", r"iphone|android|pixel|galaxy|\bsm-[a-z0-9]+", "phone", "medium"),
    DeviceSignature("tablet", r"ipad|tablet", "tablet", "medium"),
    DeviceSignature("watch", r"apple.?watch|galaxy.?watch|\bwatch\b", "watch", "medium"),
    DeviceSignature("apple-tv-service", r"_mediaremotetv\._tcp|_appletv-v2\._tcp", "tv", "high"),
    DeviceSignature("upnp-media-renderer", r"mediarenderer|avtransport|renderingcontrol", "media_player", "high"),
    DeviceSignature("upnp-internet-gateway", r"internetgatewaydevice|wanipconnection|wanpppconnection", "router", "medium"),
    DeviceSignature("upnp-printer", r"printerdevice", "printer", "high"),
    DeviceSignature("television", r"apple(?:\s+de)?[\s._-]*tv|bravia|roku|firetv|lgwebostv|television|\btv\b", "tv", "medium"),
    DeviceSignature("media-service", r"_airplay\._tcp|_googlecast\._tcp|_raop\._tcp|chromecast", "media_player", "medium"),
    DeviceSignature("speaker", r"sonos|homepod|speaker|_spotify-connect\._tcp", "speaker", "medium"),
    DeviceSignature("smart-home-service", r"_hap\._tcp|_homekit\._tcp|homekit", "smart_home", "high"),
    DeviceSignature("heat-pump", r"heat[\s_-]*pump|heatpump|air[\s_-]*conditioner|aircon|luftv[aä]rmepump", "smart_home", "medium"),
    DeviceSignature("smart-home", r"meross|roborock|shelly|tasmota|zigbee.?bridge|home.?assistant|homebridge|philips.?hue|hue.?bridge", "smart_home", "medium"),
    DeviceSignature("microcontroller", r"espressif|esp(?:32|8266)?|esphome|tasmota|shelly", "microcontroller", "medium"),
    DeviceSignature("raspberry-pi", r"raspberry|raspi|raspberrypi|\brpi\b", "raspberry_pi", "medium"),
    DeviceSignature("printer", r"printer|laserjet|officejet", "printer", "medium"),
    DeviceSignature("camera", r"camera|reolink|unifi.?protect|doorbell|arlo|eufy.?cam|tapo.?cam", "camera", "medium"),
    DeviceSignature("console", r"playstation|xbox|nintendo|switch", "console", "medium"),
    DeviceSignature("computer", r"macbook|imac|\bdesktop\b|\blaptop\b|\bpc\b|workstation|windows.?pc", "computer", "medium"),
    DeviceSignature("router", r"router|gateway|zyxel|fritz", "router", "low"),
    DeviceSignature("server", r"nas|server|ubuntu|debian|fedora|_ssh\._tcp|_smb\._tcp", "server", "low"),
)

# Product-family icon rules are deliberately narrower than category inference.
# They may use a resolved vendor, an advertised model/service, or a user-owned
# alias, but they never infer an exact hardware model from a MAC address.
ICON_SIGNATURES = (
    DeviceIconSignature(
        "robot-vacuum",
        r"\broborock\b|\birobot\b|\broomba\b|\becovacs\b|\bdeebot\b|\brobot[\s_-]*vac(?:uum)?\b|\bvacuum\b",
        "vacuum",
    ),
    DeviceIconSignature(
        "garage-door",
        r"\bgarageport\b|\bgarage[\s_-]*(?:door|opener)\b|\bmsg(?:100|200)\b",
        "garage",
    ),
    DeviceIconSignature(
        "heat-pump",
        r"\bluftv[aä]rmepump\b|\bheat[\s_-]*pump\b|\bheatpump\b|\bair[\s_-]*conditioner\b|\baircon\b",
        "heat_pump",
    ),
    DeviceIconSignature(
        "vr-headset",
        r"\bmeta[\s_-]*quest\b|\boculus\b|\bquest[\s_-]*(?:2|3|pro)\b|\bvr[\s_-]*headset\b|\bvirtual[\s_-]*reality\b|(?:^|\s)vr(?:\s|$)",
        "vr_headset",
    ),
)


CATEGORY_ICON_KEYS = {
    "phone": "phone",
    "tablet": "tablet",
    "computer": "laptop",
    "tv": "tv",
    "media_player": "media_player",
    "speaker": "speaker",
    "smart_home": "iot",
    "iot": "iot",
    "camera": "camera",
    "printer": "printer",
    "router": "router",
    "access_point": "access_point",
    "server": "server",
    "raspberry_pi": "raspberry_pi",
    "microcontroller": "microcontroller",
    "console": "console",
    "watch": "watch",
    "unknown": "device_generic",
}


def device_icon_key(
    *,
    category: str,
    vendor: str | None = None,
    hostname: str | None = None,
    model: str | None = None,
    service_hints: tuple[str, ...] = (),
) -> str:
    """Resolve one stable presentation icon from already-collected local evidence.

    The backend owns this normalization so every client renders the same device
    family. Product-specific keys require strong family evidence from local
    service/model data, a user-owned alias, or a resolved vendor that itself
    identifies a narrow device family. Broad vendor names alone are not enough.
    """
    corpus = " ".join(filter(None, (hostname, model, *service_hints))).lower()
    vendor_text = (vendor or "").lower()
    identity_corpus = " ".join(part for part in (vendor_text, corpus) if part)

    apple_tv_service = re.search(r"_mediaremotetv\._tcp|_appletv-v2\._tcp", corpus)
    apple_tv_model = re.search(r"\bappletv\d", corpus)
    apple_tv_name = re.search(r"\bapple(?:\s+de)?[\s._-]*tv\b", corpus)
    if apple_tv_service or apple_tv_model:
        return "apple_tv"
    if category in {"tv", "media_player"} and "apple" in vendor_text:
        return "apple_tv"
    if apple_tv_name and ("apple" in vendor_text or "apple" in corpus):
        return "apple_tv"

    for signature in ICON_SIGNATURES:
        if re.search(signature.pattern, identity_corpus):
            return signature.icon_key

    return CATEGORY_ICON_KEYS.get(category, "device_generic")


def clean_hostname(hostname: str | None) -> str | None:
    """Make known hostname conventions readable while preserving raw hostname elsewhere."""
    if not hostname:
        return None
    raw = hostname.strip()
    if not raw or raw == "*":
        return None
    lowered = raw.lower()
    if re.fullmatch(r"(?:esp32|esp8266|esphome|android)[-_]?[0-9a-f]{4,}", lowered):
        return "ESP device" if lowered.startswith(("esp", "esphome")) else "Android device"
    words = [word for word in re.split(r"[-_.]+", raw) if word]
    if not words:
        return None
    def title(word: str) -> str:
        lower = word.lower()
        replacements = {"iphone": "iPhone", "ipad": "iPad", "ios": "iOS", "tv": "TV", "esp32": "ESP32", "wifi": "Wi-Fi", "macbook": "MacBook"}
        return replacements.get(lower, word.upper() if word.isupper() and len(word) <= 4 else word.capitalize())
    return " ".join(title(word) for word in words)


def infer_device_type(*, hostname: str | None, vendor: str | None, service_hints: tuple[str, ...] = ()) -> DeviceInference:
    corpus = " ".join(filter(None, (hostname, vendor, *service_hints))).lower()
    for signature in SIGNATURES:
        if re.search(signature.pattern, corpus):
            return DeviceInference(signature.device_type, signature.confidence, signature.identifier)
    return DeviceInference("unknown", "low", "no matching passive signature")


def friendly_description(device_type: str) -> str:
    """English presentation name; frontend owns the translated display label."""
    return {
        "phone": "Phone", "tablet": "Tablet", "computer": "Computer", "tv": "TV", "media_player": "Media player",
        "speaker": "Speaker", "smart_home": "Smart device", "iot": "Smart device", "camera": "Camera",
        "printer": "Printer", "router": "Router", "access_point": "Access point", "server": "Server",
        "raspberry_pi": "Raspberry Pi", "microcontroller": "Smart device", "console": "Console", "watch": "Watch",
    }.get(device_type, "Device")
