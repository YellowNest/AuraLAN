#!/usr/bin/env bash
set -euo pipefail

PREFIX="/opt/auralan"
STATE_DIR="/var/lib/auralan"
SERVICE_USER="auralan"
SERVICE_GROUP="auralan"
UNIT_NAME="auralan.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
ROLLBACK_DIR="/opt/.auralan-rollback"
UNIT_BACKUP="/etc/systemd/system/.auralan.service.pre-upgrade"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAGE_DIR=""
READINESS_DIR=""
STATE_PREEXISTED=0

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup_temporary() {
  [ -z "$STAGE_DIR" ] || rm -rf "$STAGE_DIR"
  [ -z "$READINESS_DIR" ] || rm -rf "$READINESS_DIR"
}

rollback_install() {
  local rc="$1"
  trap - ERR INT TERM
  set +e

  printf '\nInstallation failed; removing the incomplete AuraLAN activation...\n' >&2
  systemctl stop "$UNIT_NAME" >/dev/null 2>&1 || true
  systemctl disable "$UNIT_NAME" >/dev/null 2>&1 || true
  rm -f "$UNIT_PATH"
  systemctl daemon-reload >/dev/null 2>&1 || true
  rm -rf "$PREFIX"

  if [ "$STATE_PREEXISTED" -eq 0 ]; then
    rm -rf "$STATE_DIR"
  fi

  cleanup_temporary
  printf 'Incomplete application files and service activation were removed. You can retry the installer safely.\n' >&2
  exit "$rc"
}

wait_for_health() {
  local attempt
  for attempt in {1..20}; do
    if "$PREFIX/backend/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8787/api/v1/health", timeout=1.5) as response:
    payload = json.load(response)
    raise SystemExit(0 if response.status == 200 and payload.get("ok") is True else 1)
PY
    then
      return 0
    fi
    sleep 1
  done
  return 1
}

[ "$(id -u)" -eq 0 ] || fail "run this installer as root (sudo ./scripts/install.sh)"

for command in python3 systemctl install tar getent groupadd useradd runuser mktemp mv; do
  command -v "$command" >/dev/null 2>&1 || fail "required command is missing: $command"
done

python3 - <<'PY' || fail "Python 3.11 or newer is required"
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY

if [ -d "$ROLLBACK_DIR" ] || [ -e "$UNIT_BACKUP" ]; then
  fail "interrupted AuraLAN upgrade markers exist; inspect $ROLLBACK_DIR and $UNIT_BACKUP before attempting a clean install"
fi

if [ -f "$UNIT_PATH" ]; then
  fail "$UNIT_PATH already exists; use scripts/upgrade.sh for an existing canonical installation"
fi

if [ -d "$PREFIX" ] && [ -n "$(find "$PREFIX" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  fail "$PREFIX already contains files; installer only performs clean installs"
fi

SOURCE_IS_GIT=0
if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  SOURCE_IS_GIT=1
  [ -z "$(git -C "$ROOT_DIR" status --porcelain --untracked-files=normal)" ] ||
    fail "source Git worktree is dirty; commit, stash, or remove local changes before installing"
fi

if [ -d "$STATE_DIR" ]; then
  STATE_PREEXISTED=1
fi

if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
  groupadd --system "$SERVICE_GROUP"
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd \
    --system \
    --gid "$SERVICE_GROUP" \
    --home-dir "$STATE_DIR" \
    --shell /usr/sbin/nologin \
    "$SERVICE_USER"
fi

install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$STATE_DIR"

STAGE_DIR="$(mktemp -d /opt/.auralan-install.XXXXXX)"
READINESS_DIR="$(mktemp -d /tmp/auralan-install-readiness.XXXXXX)"
trap cleanup_temporary EXIT

if [ "$SOURCE_IS_GIT" -eq 1 ]; then
  git -C "$ROOT_DIR" archive --format=tar HEAD | tar -xf - -C "$STAGE_DIR"
else
  tar \
    --exclude='.git' \
    --exclude='backend/.venv' \
    --exclude='node_modules' \
    --exclude='screenshots' \
    --exclude='ui-screenshots' \
    --exclude='test-results' \
    -cf - -C "$ROOT_DIR" . | tar -xf - -C "$STAGE_DIR"
fi

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$STAGE_DIR" "$READINESS_DIR"

printf 'Building isolated runtime environment...\n'
runuser -u "$SERVICE_USER" -- python3 -m venv "$STAGE_DIR/backend/.venv"
runuser -u "$SERVICE_USER" -- "$STAGE_DIR/backend/.venv/bin/python" -m pip install -r "$STAGE_DIR/backend/requirements.txt"

printf 'Checking clean state readiness before activation...\n'
runuser -u "$SERVICE_USER" -- "$STAGE_DIR/backend/.venv/bin/python" \
  "$STAGE_DIR/scripts/check-state-readiness.py" "$READINESS_DIR"

if [ -d "$PREFIX" ]; then
  rmdir "$PREFIX" || fail "$PREFIX is not empty"
fi

trap 'rollback_install $?' ERR
trap 'rollback_install 130' INT
trap 'rollback_install 143' TERM

printf 'Activating AuraLAN...\n'
mv "$STAGE_DIR" "$PREFIX"
STAGE_DIR=""

install -m 0644 "$PREFIX/systemd/auralan.service" "$UNIT_PATH"
systemctl daemon-reload
systemctl enable --now "$UNIT_NAME"

printf 'Waiting for AuraLAN state-aware health check...\n'
if ! wait_for_health; then
  systemctl --no-pager --full status "$UNIT_NAME" || true
  false
fi

[ "$(systemctl is-active "$UNIT_NAME")" = "active" ] || false

trap - ERR INT TERM
rm -rf "$READINESS_DIR"
READINESS_DIR=""

printf '\nAuraLAN installed.\n'
printf 'Service: %s\n' "$(systemctl is-active "$UNIT_NAME" 2>/dev/null || true)"
printf 'Local URL: http://127.0.0.1:8787\n'
printf 'For LAN access, configure /etc/default/auralan or a reverse proxy.\n'
