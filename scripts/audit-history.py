#!/usr/bin/env python3
"""Audit reachable Git history for credentials and machine-specific private data."""

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
    "WireGuard private key": re.compile(
        r"(?im)^\s*(?:PrivateKey|PresharedKey)\s*=\s*[A-Za-z0-9+/]{42,44}={0,2}\s*$"
    ),
    "credential-bearing URL": re.compile(
        r"(?i)https?://[^\s/:@]+:[^\s/@]+@[^\s/]+"
    ),
    "literal bearer authorization": re.compile(
        r"(?i)Authorization\s*[:=]\s*Bearer\s+[A-Za-z0-9._~+/=-]{16,}"
    ),
    "RFC1918/private IPv4 address": re.compile(
        r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|"
        r"192\.168\.(?:\d{1,3}\.)\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})\b"
    ),
    "machine-specific Linux home path": re.compile(
        r"/home/[A-Za-z0-9_.-]+(?:/|\b)"
    ),
    "machine-specific macOS home path": re.compile(
        r"/Users/[A-Za-z0-9_.-]+(?:/|\b)"
    ),
    "machine-specific Windows user path": re.compile(
        r"(?i)\b[A-Z]:\\Users\\[A-Za-z0-9_. -]+\\"
    ),
}

sensitive_names = re.compile(
    r"(^|/)(?:"
    r"\.env(?:\..+)?|"
    r"credentials\.(?:json|ya?ml)|"
    r"secrets?\.(?:json|ya?ml)|"
    r".+\.(?:pem|key|p12|pfx|sqlite|sqlite3|db|pcap|pcapng|har|log)"
    r")$",
    re.IGNORECASE,
)

# Before the privacy guard existed, two synthetic unit-test fixtures used
# conventional private-network and example home-directory values. The later cleanup commits also
# contain those literals as removed lines. These four exact commit/path findings
# are reviewed and intentionally exempted; no real host identifier is stored
# here, and every other matching occurrence on every reachable ref still fails.
known_benign_history_findings = {
    (
        "RFC1918/private IPv4 address",
        "11a5c91f8e94e866c6c9f037febf7bf3ea1ae19a",
        "backend/tests/test_probe.py",
    ),
    (
        "RFC1918/private IPv4 address",
        "23ee08e87cf4da564f86d60250c68ecebf2f72bf",
        "backend/tests/test_probe.py",
    ),
    (
        "machine-specific Linux home path",
        "e16f9849e209869bd0253c621e138a2d26e9323f",
        "backend/tests/test_persistence.py",
    ),
    (
        "machine-specific Linux home path",
        "e63c1b6225abd580f46fb7eb956af5c936fd8756",
        "backend/tests/test_persistence.py",
    ),
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, errors="replace")


def self_test() -> None:
    """Ensure the high-confidence privacy guards cannot silently regress."""
    samples = {
        "RFC1918/private IPv4 address": "192" + ".168.44.9",
        "machine-specific Linux home path": "/home/" + "operator" + "/auralan/state",
        "machine-specific macOS home path": "/Users/" + "operator" + "/Downloads/report.txt",
        "machine-specific Windows user path": "C:" + "\\Users\\" + "Operator" + "\\Desktop\\report.txt",
        "WireGuard private key": "PrivateKey = " + ("A" * 43) + "=",
        "credential-bearing URL": "https://user:" + "password" + "@example.invalid/path",
        "literal bearer authorization": "Authorization: Bearer " + ("a" * 24),
    }
    for label, sample in samples.items():
        if not patterns[label].search(sample):
            raise SystemExit(f"AuraLAN history audit self-test FAILED: {label}")


def main() -> int:
    self_test()
    errors: list[str] = []

    names = git("log", "--all", "--name-only", "--format=").splitlines()
    for name in sorted({item.strip() for item in names if item.strip()}):
        if sensitive_names.search(name) and name != ".env.example":
            errors.append(f"sensitive filename existed in reachable history: {name}")

    # Include commit messages as well as textual patches. A secret or local
    # machine identifier is still public if it only appears in Git metadata or
    # in a file version that was later deleted.
    history_text = git(
        "log",
        "--all",
        "-p",
        "--format=commit %H%n%B",
        "--no-ext-diff",
        "--text",
    )
    commit_markers = list(re.finditer(r"(?m)^commit ([0-9a-f]{40})$", history_text))

    for label, pattern in patterns.items():
        findings: set[tuple[str, str]] = set()

        for match in pattern.finditer(history_text):
            commit_sha = "unknown"
            commit_start = 0
            for marker in commit_markers:
                if marker.start() > match.start():
                    break
                commit_sha = marker.group(1)
                commit_start = marker.end()

            location = "<commit message>"
            diff_start = history_text.rfind("\ndiff --git ", commit_start, match.start())
            if diff_start >= commit_start:
                header_end = history_text.find("\n", diff_start + 1)
                header = history_text[diff_start + 1:header_end]
                parsed = re.match(r"diff --git a/(.+?) b/(.+)$", header)
                if parsed:
                    location = parsed.group(2)

            findings.add((commit_sha, location))

        for commit_sha, location in sorted(findings):
            if (label, commit_sha, location) in known_benign_history_findings:
                continue
            errors.append(
                f"possible {label} found in reachable history "
                f"at commit {commit_sha} ({location})"
            )

    if errors:
        print("AuraLAN history audit FAILED:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print("AuraLAN history audit OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
