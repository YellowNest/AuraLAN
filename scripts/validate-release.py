#!/usr/bin/env python3
"""Dependency-free release checks for AuraLAN.

This intentionally validates repository hygiene and frontend contracts without
requiring Node, a browser, network access, or production credentials.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

errors: list[str] = []


def validate_shell_scripts() -> None:
    for path in sorted((ROOT / "scripts").glob("*.sh")):
        try:
            result = subprocess.run(
                ["bash", "-n", str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            fail(f"could not syntax-check {path.relative_to(ROOT)}: {type(exc).__name__}")
            continue
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            suffix = f": {detail[-1]}" if detail else ""
            fail(f"shell syntax check failed for {path.relative_to(ROOT)}{suffix}")


def fail(message: str) -> None:
    errors.append(message)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read {path.relative_to(ROOT)}: {type(exc).__name__}")
        return ""


def parse_json(path: Path) -> dict:
    try:
        value = json.loads(read(path))
    except (ValueError, TypeError) as exc:
        fail(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
        return {}
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
        return {}
    return value


project = parse_json(ROOT / "project.json")
manifest = parse_json(FRONTEND / "manifest.webmanifest")
validate_shell_scripts()

if project.get("productName") != "AuraLAN" or project.get("shortName") != "AuraLAN":
    fail("project.json must use the canonical AuraLAN product name")
if manifest.get("short_name") != "AuraLAN":
    fail("manifest short_name must be AuraLAN")

version = str(project.get("version") or "")
if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?", version):
    fail("project.json version must be Semantic Versioning compatible")

brand_source = read(ROOT / "backend/app/brand.py")
frontend_brand_source = read(FRONTEND / "js/brand.js")
if version and f'"version": "{version}"' not in brand_source:
    fail("backend brand fallback version is out of sync with project.json")
for key in ("productName", "shortName", "tagline", "apiVersion"):
    value = str(project.get(key) or "")
    if value and value not in brand_source:
        fail(f"backend brand fallback is out of sync for {key}")
    if value and value not in frontend_brand_source:
        fail(f"frontend brand fallback is out of sync for {key}")
accent = project.get("accent") or {}
for value in (accent.get("primary"), accent.get("soft")):
    if value and str(value) not in brand_source:
        fail("backend brand fallback accent is out of sync with project.json")
    if value and str(value) not in frontend_brand_source:
        fail("frontend brand fallback accent is out of sync with project.json")

changelog_source = read(ROOT / "CHANGELOG.md")
if "## [Unreleased]" not in changelog_source:
    fail("CHANGELOG.md must contain an Unreleased section")
if version and "-dev" not in version and f"## [{version}] -" not in changelog_source:
    fail(f"final version {version} is missing a dated CHANGELOG release section")

license_source = read(ROOT / "LICENSE")
if "MIT License" not in license_source or "Copyright (c) 2026 YellowNest" not in license_source:
    fail("stable releases must retain the selected MIT license and copyright notice")

runtime_files = [
    ROOT / "project.json",
    ROOT / "backend/app/brand.py",
    ROOT / "backend/app/main.py",
    ROOT / "backend/app/models.py",
    ROOT / "backend/app/services/system.py",
    FRONTEND / "index.html",
    FRONTEND / "app.js",
    FRONTEND / "app.css",
    FRONTEND / "manifest.webmanifest",
    FRONTEND / "js/brand.js",
    FRONTEND / "js/data.js",
    FRONTEND / "js/device-names.js",
    FRONTEND / "js/device-icons.js",
    FRONTEND / "js/i18n.js",
    FRONTEND / "js/icons.js",
]

for path in runtime_files:
    source = read(path)
    if "Auralan" in source:
        fail(f"legacy Auralan casing remains in {path.relative_to(ROOT)}")

network_runtime_files = [
    FRONTEND / "index.html",
    FRONTEND / "app.js",
    FRONTEND / "app.css",
    FRONTEND / "manifest.webmanifest",
    FRONTEND / "js/brand.js",
    FRONTEND / "js/data.js",
    FRONTEND / "js/device-names.js",
    FRONTEND / "js/device-icons.js",
    FRONTEND / "js/i18n.js",
    FRONTEND / "js/icons.js",
]
for path in network_runtime_files:
    if re.search(r"https?://", read(path), re.IGNORECASE):
        fail(f"external runtime URL found in {path.relative_to(ROOT)}")

app_source = read(FRONTEND / "app.js")
i18n_source = read(FRONTEND / "js/i18n.js")
device_names_source = read(FRONTEND / "js/device-names.js")
device_icons_source = read(FRONTEND / "js/device-icons.js")

for unwanted in ("Unknown device", "Okänd enhet"):
    if unwanted in i18n_source or unwanted in device_names_source:
        fail(f"generic device-list wording returned: {unwanted}")

match = re.search(
    r"en:\s*\{(?P<en>.*?)\}\s*,\s*sv:\s*\{(?P<sv>.*?)\}\s*\}\s*;",
    i18n_source,
    re.DOTALL,
)
if not match:
    fail("could not parse translation dictionaries")
else:
    key_pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:")
    en_keys = set(key_pattern.findall(match.group("en")))
    sv_keys = set(key_pattern.findall(match.group("sv")))
    only_en = sorted(en_keys - sv_keys)
    only_sv = sorted(sv_keys - en_keys)
    if only_en:
        fail("Swedish translations missing: " + ", ".join(only_en))
    if only_sv:
        fail("English translations missing: " + ", ".join(only_sv))

    used_keys = set(re.findall(r"\bt\(\s*['\"]([^'\"]+)['\"]", app_source))
    missing_en = sorted(used_keys - en_keys)
    missing_sv = sorted(used_keys - sv_keys)
    if missing_en:
        fail("English runtime translations missing: " + ", ".join(missing_en))
    if missing_sv:
        fail("Swedish runtime translations missing: " + ", ".join(missing_sv))

css_source = read(FRONTEND / "app.css")
if css_source.count("{") != css_source.count("}"):
    fail("frontend/app.css has unbalanced braces")

index_source = read(FRONTEND / "index.html")
viewport_match = re.search(r'<meta\s+name=["\']viewport["\']\s+content=["\']([^"\']+)["\']', index_source)
if not viewport_match:
    fail("frontend/index.html is missing the mobile viewport meta tag")
else:
    viewport = viewport_match.group(1)
    for required in ("width=device-width", "initial-scale=1", "maximum-scale=1", "user-scalable=no", "viewport-fit=cover"):
        if required not in viewport:
            fail(f"mobile viewport is missing required setting: {required}")

if "network-orbit" in app_source or "network-orbit" in css_source:
    fail("retired decorative network-orbit UI returned")

if "renderActivity" not in app_source or "activity-center-list" not in app_source:
    fail("frontend is missing the first-class Activity Center")
if "['activity', 'uptime']" not in app_source:
    fail("Activity Center is missing from primary navigation")
if ".activity-overview" not in css_source or ".activity-filter-row" not in css_source:
    fail("Activity Center responsive styling is missing")
if "grid-template-columns:repeat(6,minmax(0,1fr))" not in css_source:
    fail("mobile navigation does not reserve a slot for all six primary views")
if index_source.count("<span>Activity</span>") != 2:
    fail("static desktop/mobile navigation must expose Activity before JavaScript boot")

device_store_source = read(ROOT / "backend/app/persistence/device_store.py")
if "service_exposure_changed" not in device_store_source or "baseline_captured" not in device_store_source:
    fail("persistent Activity Center event sources are incomplete")
if "NOTIFICATION_EVENT_TYPES" not in device_store_source:
    fail("richer local activity must remain explicitly separated from webhook event delivery")

deploy_local_source = read(ROOT / "scripts/deploy-local.sh")
for token in ("backup_database", "check_target_state_readiness", "restore_database", "rollback_deployment"):
    if token not in deploy_local_source:
        fail(f"checkout-backed deployment is missing database-safe rollback step: {token}")

if "@media(max-width:760px)" not in css_source:
    fail("frontend/app.css is missing the primary mobile layout breakpoint")
if css_source.count("@media(max-width:760px){") != 1:
    fail("frontend/app.css must have exactly one canonical mobile layout block")
if ".mobile-topbar" not in css_source or ".mobile-connection-state" not in css_source:
    fail("mobile header structure is missing from frontend/app.css")
if 'class="mobile-topbar"' not in index_source or index_source.count("data-connection-state") != 2:
    fail("frontend/index.html must expose separate mobile and desktop connection status placements")
if "modal-open" not in app_source or "modal-open" not in css_source:
    fail("modal sheets must lock the page behind them")
if "overscroll-behavior-y:contain" not in css_source:
    fail("mobile sheets must contain overscroll instead of chaining into the page")
if ".inspector-heading" not in css_source:
    fail("detail sheets are missing the unified inspector heading")
for token in ("--type-micro", "--type-caption", "--type-body", "--type-card", "--type-section", "--type-page"):
    if token not in css_source:
        fail(f"frontend typography scale is missing token: {token}")
if "Canonical typography scale" not in css_source:
    fail("frontend/app.css is missing the canonical typography layer")
if (
    "device-list-head" not in app_source
    or "device-ip" not in app_source
    or "device-mobile-ip" not in app_source
    or "device-location" not in app_source
    or "friendlyDeviceContext" not in app_source
):
    fail("device list is missing its friendly identity, IP, or location hierarchy")
if "friendlyDeviceListIdentity" in app_source or 'class="device-mac"' in app_source or "device-mobile-identity" in app_source:
    fail("default device list must keep MAC/technical identity in search and device details instead of mixing it into the friendly row")
if 'name="category_override"' in app_source or "useDetectedType" in app_source:
    fail("frontend still exposes the removed manual device category selector")
if "deviceIconKey" not in app_source or "icon_key" not in app_source:
    fail("device list is missing normalized icon-key rendering")
if "const deviceIcon =" in app_source:
    fail("legacy text-guessing device icon resolver returned")
if "apple_tv" not in device_icons_source:
    fail("device icon resolver is missing the Apple TV family")
for required_icon in ("vacuum", "garage", "heat_pump", "vr_headset"):
    if required_icon not in device_icons_source:
        fail(f"device icon resolver is missing product-family key: {required_icon}")

device_backend_source = read(ROOT / "backend/app/discovery/network/devices.py")
device_models_source = read(ROOT / "backend/app/models.py")
if '"uplink": "ethernet"' in device_backend_source:
    fail("client medium must not be inferred from AuraLAN's Ethernet uplink")
if '"icon_key": icon_key' not in device_backend_source or "icon_key: DeviceIconKey" not in device_models_source:
    fail("backend device contract is missing normalized icon keys")

icons_source = read(FRONTEND / "js/icons.js")
if "apple_tv:" not in icons_source:
    fail("local icon family is missing the Apple TV glyph")
for required_icon in ("vacuum:", "garage:", "heat_pump:", "vr_headset:"):
    if required_icon not in icons_source:
        fail(f"local icon family is missing glyph: {required_icon.removesuffix(':')}")
for asset in sorted(set(re.findall(r"/assets/assets/services/([^'\"]+\.svg)", icons_source))):
    if not (FRONTEND / "assets/services" / asset).is_file():
        fail(f"missing service asset: frontend/assets/services/{asset}")

for icon_entry in manifest.get("icons", []):
    if not isinstance(icon_entry, dict):
        continue
    src = str(icon_entry.get("src") or "")
    if not src:
        fail("manifest icon entry has no src")
        continue
    if src.startswith("/assets/"):
        target = FRONTEND / src.removeprefix("/assets/")
    else:
        target = FRONTEND / src.lstrip("/")
    if not target.is_file():
        fail(f"manifest icon does not exist: {src}")

try:
    tracked_raw = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        stderr=subprocess.DEVNULL,
    )
    tracked = [Path(item.decode("utf-8")) for item in tracked_raw.split(b"\0") if item]
except (OSError, subprocess.CalledProcessError):
    fail("could not inspect tracked files with git")
    tracked = []

sensitive_extensions = {
    ".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3",
    ".db", ".pcap", ".pcapng", ".har", ".log",
}
for path in tracked:
    lower_name = path.name.lower()
    suffix = path.suffix.lower()
    if lower_name == ".env" or (lower_name.startswith(".env.") and lower_name != ".env.example"):
        fail(f"sensitive environment file is tracked: {path}")
    if suffix in sensitive_extensions:
        fail(f"sensitive/runtime file type is tracked: {path}")
    if lower_name.startswith("secrets.") or lower_name in {"credentials.json", "credentials.yaml", "credentials.yml"}:
        fail(f"sensitive credential file is tracked: {path}")

secret_patterns = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "Stripe live key": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
}
text_suffixes = {
    ".py", ".js", ".mjs", ".css", ".html", ".md", ".json", ".yaml",
    ".yml", ".sh", ".service", ".webmanifest", ".txt", ".example",
}
for path in tracked:
    full = ROOT / path
    if full.suffix.lower() not in text_suffixes or not full.is_file():
        continue
    source = read(full)
    for label, pattern in secret_patterns.items():
        if pattern.search(source):
            fail(f"possible {label} found in tracked file: {path}")

# Public fixtures/docs must never carry machine-specific home paths or RFC1918
# addresses copied from a live installation. Use RFC 5737 documentation ranges.
public_fixture_prefixes = (
    "README.md", "CONTRIBUTING.md", "SECURITY.md", "docs/",
    "caddy/", "backend/tests/", "frontend/tests/",
)
private_ipv4 = re.compile(
    r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.(?:\d{1,3}\.)\d{1,3}|"
    r"172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})\b"
)
for path in tracked:
    portable = path.as_posix()
    if not portable.startswith(public_fixture_prefixes):
        continue
    full = ROOT / path
    if full.suffix.lower() not in text_suffixes or not full.is_file():
        continue
    source = read(full)
    if re.search(r"/home/[A-Za-z0-9_.-]+/", source):
        fail(f"machine-specific home path found in public fixture: {path}")
    if private_ipv4.search(source):
        fail(f"private LAN address found in public fixture: {path}")

backend_runtime = sorted((ROOT / "backend/app").rglob("*.py"))
for path in backend_runtime:
    source = read(path)
    if re.search(r"['\"](?:wlan0|eth0|wg0)['\"]", source):
        fail(f"production discovery assumes a conventional interface name in {path.relative_to(ROOT)}")
    if "/home/" in source or "/opt/stacks/" in source:
        fail(f"machine-specific installation path found in {path.relative_to(ROOT)}")

# Whole-tree branding guard plus portability checks. The validator itself
# necessarily contains portability test literals, so only those checks skip it.
# The obsolete pre-AuraLAN brand is assembled at runtime so even this validator
# contains no literal occurrence of that retired name.
legacy_brand = "".join(("pi", "net"))
for path in tracked:
    full = ROOT / path
    if full.suffix.lower() not in text_suffixes or not full.is_file():
        continue
    source = read(full)
    if legacy_brand in source.lower():
        fail(f"legacy pre-AuraLAN branding found in tracked source: {path}")
    if path == Path("scripts/validate-release.py"):
        continue
    if private_ipv4.search(source):
        fail(f"RFC1918/private LAN literal found in tracked source: {path}")
    if re.search(r"/home/[A-Za-z0-9_.-]+/", source):
        fail(f"machine-specific home path found in tracked source: {path}")
    if "/opt/stacks/" in source:
        fail(f"deployment-specific stack path found in tracked source: {path}")
    if re.search(r"\b(?:wlan0|eth0|wg0)\b", source):
        fail(f"conventional interface fixture found in tracked source: {path}")
    if "Auralan" in source:
        fail(f"legacy product casing found in tracked source: {path}")

if errors:
    print("AuraLAN release validation FAILED:", file=sys.stderr)
    for error in errors:
        print(f" - {error}", file=sys.stderr)
    raise SystemExit(1)

print("AuraLAN release validation OK")
