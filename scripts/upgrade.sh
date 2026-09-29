#!/usr/bin/env bash
set -euo pipefail

PREFIX="/opt/auralan"
ROLLBACK_DIR="/opt/.auralan-rollback"
STATE_DEFAULT="/var/lib/auralan"
ENV_FILE="/etc/default/auralan"
UNIT_NAME="auralan.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
UNIT_BACKUP="/etc/systemd/system/.auralan.service.pre-upgrade"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAGE_DIR=""
DB_BACKUP=""
DESTRUCTIVE=0

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

read_env_value() {
  local key="$1"
  python3 - "$ENV_FILE" "$key" <<'PY'
from __future__ import annotations

import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
wanted = sys.argv[2]
value = ""
try:
    lines = path.read_text(encoding="utf-8").splitlines()
except OSError:
    lines = []

for raw in lines:
    line = raw.strip()
    if not line or line.startswith(("#", ";")) or "=" not in line:
        continue
    key, candidate = line.split("=", 1)
    if key.strip() != wanted:
        continue
    try:
        parts = shlex.split(candidate, posix=True)
    except ValueError:
        continue
    if len(parts) == 1:
        value = parts[0]

print(value)
PY
}

health_url() {
  if [ -n "${AURALAN_HEALTH_URL:-}" ]; then
    printf '%s\n' "$AURALAN_HEALTH_URL"
    return
  fi
  local port
  port="${AURALAN_PORT:-}"
  if [ -z "$port" ]; then
    port="$(read_env_value AURALAN_PORT)"
  fi
  port="${port:-8787}"
  printf 'http://127.0.0.1:%s/api/v1/health\n' "$port"
}

wait_for_health() {
  local url="$1"
  local python="$2"
  local attempt
  for attempt in {1..20}; do
    if "$python" - "$url" <<'PY' >/dev/null 2>&1
import json
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=1.5) as response:
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

restore_database() {
  [ -n "$DB_BACKUP" ] || return 0
  [ -f "$DB_BACKUP" ] || return 0

  local data_dir db_path
  data_dir="$(dirname "$DB_BACKUP")"
  data_dir="$(dirname "$data_dir")"
  db_path="$data_dir/auralan.db"

  rm -f "$db_path-wal" "$db_path-shm"
  cp -f "$DB_BACKUP" "$db_path"
  chown "$SERVICE_USER:$SERVICE_GROUP" "$db_path"
  chmod 0640 "$db_path"
}

rollback() {
  local rc="$1"
  trap - ERR INT TERM
  set +e

  printf '\nUpgrade failed; restoring the previous AuraLAN installation...\n' >&2
  systemctl stop "$UNIT_NAME" >/dev/null 2>&1 || true

  if [ -d "$PREFIX" ] && [ -d "$ROLLBACK_DIR" ]; then
    rm -rf "$PREFIX"
  fi
  if [ ! -d "$PREFIX" ] && [ -d "$ROLLBACK_DIR" ]; then
    mv "$ROLLBACK_DIR" "$PREFIX"
  fi

  if [ -f "$UNIT_BACKUP" ]; then
    cp -f "$UNIT_BACKUP" "$UNIT_PATH"
  fi

  restore_database
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl start "$UNIT_NAME" >/dev/null 2>&1 || true

  if [ -x "$PREFIX/backend/.venv/bin/python" ]; then
    wait_for_health "$(health_url)" "$PREFIX/backend/.venv/bin/python" >/dev/null 2>&1 || true
  fi

  [ -z "$STAGE_DIR" ] || rm -rf "$STAGE_DIR"
  printf 'Previous installation restored.\n' >&2
  exit "$rc"
}

cleanup_stage() {
  [ -z "$STAGE_DIR" ] || rm -rf "$STAGE_DIR"
}

[ "$(id -u)" -eq 0 ] || fail "run this upgrader as root (sudo ./scripts/upgrade.sh)"

for command in python3 systemctl install tar getent runuser mktemp cp mv; do
  command -v "$command" >/dev/null 2>&1 || fail "required command is missing: $command"
done

[ -d "$PREFIX" ] || fail "$PREFIX does not exist; use scripts/install.sh for a clean installation"
[ -f "$UNIT_PATH" ] || fail "$UNIT_PATH does not exist; this upgrader only supports the canonical systemd installation"
[ -f "$ROOT_DIR/project.json" ] || fail "project.json is missing from the upgrade source"

SERVICE_USER="$(systemctl show "$UNIT_NAME" -p User --value 2>/dev/null || true)"
SERVICE_GROUP="$(systemctl show "$UNIT_NAME" -p Group --value 2>/dev/null || true)"
SERVICE_USER="${SERVICE_USER:-auralan}"
SERVICE_GROUP="${SERVICE_GROUP:-auralan}"

id "$SERVICE_USER" >/dev/null 2>&1 || fail "service user does not exist: $SERVICE_USER"
getent group "$SERVICE_GROUP" >/dev/null 2>&1 || fail "service group does not exist: $SERVICE_GROUP"

TARGET_VERSION="$(python3 - "$ROOT_DIR/project.json" <<'PY'
import json
import sys
from pathlib import Path

project = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(str(project.get("version") or ""))
PY
)"
[ -n "$TARGET_VERSION" ] || fail "could not read target version"
if [[ "$TARGET_VERSION" == *-dev* ]] && [ "${AURALAN_ALLOW_DEV_UPGRADE:-0}" != "1" ]; then
  fail "refusing to install development version $TARGET_VERSION; set AURALAN_ALLOW_DEV_UPGRADE=1 only for intentional testing"
fi

printf 'Validating AuraLAN %s before staging...\n' "$TARGET_VERSION"
python3 "$ROOT_DIR/scripts/validate-release.py"

DATA_DIR="${AURALAN_DATA_DIR:-}"
if [ -z "$DATA_DIR" ]; then
  DATA_DIR="$(read_env_value AURALAN_DATA_DIR)"
fi
DATA_DIR="${DATA_DIR:-$STATE_DEFAULT}"
case "$DATA_DIR" in
  /*) ;;
  *) fail "AURALAN_DATA_DIR must be an absolute path for safe upgrades" ;;
esac

if [ -d "$ROLLBACK_DIR" ]; then
  fail "$ROLLBACK_DIR exists from an interrupted upgrade; restore or remove it before continuing"
fi
if [ -e "$UNIT_BACKUP" ]; then
  fail "$UNIT_BACKUP exists from an interrupted upgrade; inspect it before continuing"
fi

trap cleanup_stage EXIT

STAGE_DIR="$(mktemp -d /opt/.auralan-stage.XXXXXX)"

if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
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

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$STAGE_DIR"

printf 'Building isolated runtime environment...\n'
runuser -u "$SERVICE_USER" -- python3 -m venv "$STAGE_DIR/backend/.venv"
runuser -u "$SERVICE_USER" -- "$STAGE_DIR/backend/.venv/bin/python" -m pip install -r "$STAGE_DIR/backend/requirements.txt"

printf 'Running backend regression tests in staged code...\n'
(
  cd "$STAGE_DIR/backend"
  runuser -u "$SERVICE_USER" -- "$STAGE_DIR/backend/.venv/bin/python" -m unittest discover -s tests -v
)

if [ -f "$DATA_DIR/auralan.db" ]; then
  install -d -m 0700 "$DATA_DIR/.upgrade-backups"
  DB_BACKUP="$DATA_DIR/.upgrade-backups/auralan-pre-upgrade.db"
  DB_TMP="$DB_BACKUP.tmp"
  rm -f "$DB_TMP"

  printf 'Creating consistent SQLite backup...\n'
  python3 - "$DATA_DIR/auralan.db" "$DB_TMP" <<'PY'
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
src = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, timeout=5.0)
dst = sqlite3.connect(target)
try:
    src.backup(dst)
    result = dst.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise SystemExit("SQLite backup integrity_check failed")
finally:
    dst.close()
    src.close()
PY
  chmod 0600 "$DB_TMP"
  mv -f "$DB_TMP" "$DB_BACKUP"
fi

cp -f "$UNIT_PATH" "$UNIT_BACKUP"

printf 'Switching application code...\n'
DESTRUCTIVE=1
trap 'rollback $?' ERR
trap 'rollback 130' INT
trap 'rollback 143' TERM

systemctl stop "$UNIT_NAME"
mv "$PREFIX" "$ROLLBACK_DIR"
mv "$STAGE_DIR" "$PREFIX"
STAGE_DIR=""

install -m 0644 "$PREFIX/systemd/auralan.service" "$UNIT_PATH"
systemctl daemon-reload
systemctl start "$UNIT_NAME"

URL="$(health_url)"
printf 'Waiting for %s...\n' "$URL"
if ! wait_for_health "$URL" "$PREFIX/backend/.venv/bin/python"; then
  false
fi

[ "$(systemctl is-active "$UNIT_NAME")" = "active" ] || false

trap - ERR INT TERM
DESTRUCTIVE=0
rm -rf "$ROLLBACK_DIR"
rm -f "$UNIT_BACKUP"

printf '\nAuraLAN upgraded successfully.\n'
printf 'Version: %s\n' "$TARGET_VERSION"
printf 'Service: %s\n' "$(systemctl is-active "$UNIT_NAME" 2>/dev/null || true)"
printf 'State preserved at: %s\n' "$DATA_DIR"
if [ -n "$DB_BACKUP" ]; then
  printf 'Pre-upgrade database backup: %s\n' "$DB_BACKUP"
fi
