#!/usr/bin/env bash
set -euo pipefail

PREFIX="/opt/auralan"
STATE_DIR="/var/lib/auralan"
SERVICE_USER="auralan"
SERVICE_GROUP="auralan"
UNIT_NAME="auralan.service"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[ "$(id -u)" -eq 0 ] || fail "run this installer as root (sudo ./scripts/install.sh)"

for command in python3 systemctl install tar getent groupadd useradd runuser; do
  command -v "$command" >/dev/null 2>&1 || fail "required command is missing: $command"
done

python3 - <<'PY' || fail "Python 3.11 or newer is required"
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY

if [ -d "$PREFIX" ] && [ -n "$(find "$PREFIX" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  fail "$PREFIX already contains files; installer only performs clean installs"
fi

if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
  groupadd --system "$SERVICE_GROUP"
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd     --system     --gid "$SERVICE_GROUP"     --home-dir "$STATE_DIR"     --shell /usr/sbin/nologin     "$SERVICE_USER"
fi

install -d -m 0755 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$PREFIX"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$STATE_DIR"

TMP_DIR="$(mktemp -d /tmp/auralan-install.XXXXXX)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT_DIR" archive --format=tar HEAD | tar -xf - -C "$TMP_DIR"
else
  tar     --exclude='.git'     --exclude='backend/.venv'     --exclude='node_modules'     --exclude='screenshots'     --exclude='ui-screenshots'     --exclude='test-results'     -cf - -C "$ROOT_DIR" . | tar -xf - -C "$TMP_DIR"
fi

cp -a "$TMP_DIR/." "$PREFIX/"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$PREFIX"

if command -v runuser >/dev/null 2>&1; then
  runuser -u "$SERVICE_USER" -- python3 -m venv "$PREFIX/backend/.venv"
  runuser -u "$SERVICE_USER" -- "$PREFIX/backend/.venv/bin/python" -m pip install -r "$PREFIX/backend/requirements.txt"
else
  fail "runuser is required to build the service virtual environment safely"
fi

install -m 0644 "$PREFIX/systemd/auralan.service" "/etc/systemd/system/$UNIT_NAME"
systemctl daemon-reload
systemctl enable --now "$UNIT_NAME"

printf 'Waiting for AuraLAN health check...\n'
healthy=0
for _ in {1..15}; do
  if "$PREFIX/backend/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:8787/api/v1/health", timeout=1) as response:
    raise SystemExit(0 if response.status == 200 else 1)
PY
  then
    healthy=1
    break
  fi
  sleep 1
done

if [ "$healthy" -ne 1 ]; then
  systemctl --no-pager --full status "$UNIT_NAME" || true
  fail "AuraLAN did not become healthy after installation"
fi

printf '\nAuraLAN installed.\n'
printf 'Service: %s\n' "$(systemctl is-active "$UNIT_NAME" 2>/dev/null || true)"
printf 'Local URL: http://127.0.0.1:8787\n'
printf 'For LAN access, configure /etc/default/auralan or a reverse proxy.\n'
