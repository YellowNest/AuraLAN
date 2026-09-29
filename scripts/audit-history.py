#!/usr/bin/env python3
"""Audit reachable Git history for high-confidence secret material."""

from __future__ import annotations

import re
import subprocess
import sys

patterns = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "Stripe live key": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
}

sensitive_names = re.compile(
    r"(^|/)(?:\.env(?:\..+)?|credentials\.(?:json|ya?ml)|secrets?\.(?:json|ya?ml)|"
    r".+\.(?:pem|key|p12|pfx|sqlite|sqlite3|db|pcap|pcapng|har))$",
    re.IGNORECASE,
)

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, errors="replace")

errors: list[str] = []

names = git("log", "--all", "--name-only", "--format=").splitlines()
for name in sorted({item.strip() for item in names if item.strip()}):
    if sensitive_names.search(name) and name != ".env.example":
        errors.append(f"sensitive filename existed in reachable history: {name}")

patches = git("log", "--all", "-p", "--format=commit %H")
for label, pattern in patterns.items():
    match = pattern.search(patches)
    if match:
        errors.append(f"possible {label} found in reachable history")

if errors:
    print("AuraLAN history audit FAILED:", file=sys.stderr)
    for error in errors:
        print(f" - {error}", file=sys.stderr)
    raise SystemExit(1)

print("AuraLAN history audit OK")
