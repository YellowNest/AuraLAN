#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ -n "${AURALAN_SERVICE:-}" ]; then
  SERVICE_NAME="$AURALAN_SERVICE"
else
  SERVICE_NAME="auralan"
fi
HEALTH_URL="${AURALAN_HEALTH_URL:-http://127.0.0.1:8787/api/v1/health}"
VENV_PYTHON="$ROOT_DIR/backend/.venv/bin/python"
DATA_DIR=""
DB_PATH=""
DB_BACKUP=""
DB_OWNER=""
DB_GROUP=""
DB_MODE=""
READINESS_DIR=""

cd "$ROOT_DIR"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

health_json() {
  curl -fsS --max-time 2 "$HEALTH_URL" 2>/dev/null
}

wait_for_health() {
  local attempt
  for attempt in {1..15}; do
    if health_json >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

resolve_data_dir() {
  if [ -n "${AURALAN_DATA_DIR:-}" ]; then
    printf '%s\n' "$AURALAN_DATA_DIR"
    return
  fi

  local pid from_process service_user
  pid="$(systemctl show "$SERVICE_NAME" -p MainPID --value 2>/dev/null || true)"
  if [[ "$pid" =~ ^[1-9][0-9]*$ ]]; then
    from_process="$(sudo python3 - "$pid" <<'PY'
import sys

pid = sys.argv[1]
try:
    raw = open(f"/proc/{pid}/environ", "rb").read()
except OSError:
    print("")
    raise SystemExit(0)

for entry in raw.split(b"\0"):
    if entry.startswith(b"AURALAN_DATA_DIR="):
        print(entry.split(b"=", 1)[1].decode("utf-8", "replace"))
        break
else:
    print("")
PY
)"
    if [ -n "$from_process" ]; then
      printf '%s\n' "$from_process"
      return
    fi
  fi

  service_user="$(systemctl show "$SERVICE_NAME" -p User --value 2>/dev/null || true)"
  service_user="${service_user:-root}"
  python3 - "$service_user" <<'PY'
import pwd
import sys
from pathlib import Path

home = Path(pwd.getpwnam(sys.argv[1]).pw_dir)
print(home / ".local" / "state" / "auralan")
PY
}

backup_database() {
  DATA_DIR="$(resolve_data_dir)"
  case "$DATA_DIR" in
    /*) ;;
    *) fail "resolved AuraLAN data directory is not absolute: $DATA_DIR" ;;
  esac

  DB_PATH="$DATA_DIR/auralan.db"
  if ! sudo test -f "$DB_PATH"; then
    return 0
  fi

  read -r DB_OWNER DB_GROUP DB_MODE < <(sudo stat -c '%u %g %a' "$DB_PATH")
  local backup_dir tmp
  backup_dir="$DATA_DIR/.deploy-backups"
  DB_BACKUP="$backup_dir/auralan-pre-deploy.db"
  tmp="$DB_BACKUP.tmp"

  printf 'Creating consistent SQLite backup before code activation...\n'
  sudo install -d -m 0700 "$backup_dir"
  sudo rm -f "$tmp"
  sudo "$VENV_PYTHON" - "$DB_PATH" "$tmp" <<'PY'
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
  sudo chmod 0600 "$tmp"
  sudo mv -f "$tmp" "$DB_BACKUP"
}

check_target_state_readiness() {
  [ -n "$DB_BACKUP" ] || return 0

  READINESS_DIR="$(mktemp -d /tmp/auralan-deploy-readiness.XXXXXX)"
  sudo cp -f "$DB_BACKUP" "$READINESS_DIR/auralan.db"
  sudo chown "$(id -u):$(id -g)" "$READINESS_DIR/auralan.db"
  chmod 0600 "$READINESS_DIR/auralan.db"

  printf 'Checking target code against a copy of current AuraLAN state...\n'
  "$VENV_PYTHON" "$TMPDIR_DEPLOY/scripts/check-state-readiness.py" "$READINESS_DIR"
}

restore_database() {
  [ -n "$DB_BACKUP" ] || return 0
  sudo test -f "$DB_BACKUP" || return 0

  printf 'Restoring pre-deploy SQLite state...\n' >&2
  sudo rm -f "$DB_PATH-wal" "$DB_PATH-shm"
  sudo cp -f "$DB_BACKUP" "$DB_PATH"
  sudo chown "$DB_OWNER:$DB_GROUP" "$DB_PATH"
  sudo chmod "$DB_MODE" "$DB_PATH"
}

rollback_deployment() {
  local reason="$1"
  printf '%s Rolling back code and local state...\n' "$reason" >&2
  sudo systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
  git reset --hard "$OLD_HEAD"
  restore_database
  if sudo systemctl start "$SERVICE_NAME" && wait_for_health; then
    fail "$reason; previous commit and database restored and healthy"
  fi
  fail "$reason; rollback was attempted but previous service health could not be confirmed"
}

validate_tree() {
  local tree="$1"

  printf 'Running release validation...\n'
  "$VENV_PYTHON" "$tree/scripts/validate-release.py"

  printf 'Running backend tests...\n'
  (
    cd "$tree/backend"
    "$VENV_PYTHON" -m unittest discover -s tests -v
  )

  if command -v node >/dev/null 2>&1; then
    printf 'Running frontend syntax checks...\n'
    while IFS= read -r -d '' source; do
      node --check "$source"
    done < <(find "$tree/frontend" "$tree/scripts" -type f \( -name '*.js' -o -name '*.mjs' \) -print0)

    printf 'Running frontend unit tests...\n'
    node --test "$tree/frontend/tests/"*.test.mjs
  else
    printf 'Node is not installed; dependency-free validation completed, optional frontend JS tests skipped.\n'
  fi
}

print_success() {
  local payload
  payload="$(health_json)" || fail "health endpoint became unavailable after deployment"
  printf '\nAuraLAN deployed successfully.\n'
  printf 'Commit: %s\n' "$(git rev-parse --short HEAD)"
  printf 'Service: %s\n' "$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)"
  printf 'Health: %s\n' "$payload"
}

[ "$(git branch --show-current)" = "main" ] || fail "deploy-local.sh only deploys main"
[ -z "$(git status --porcelain)" ] || fail "working tree is not clean"
git remote get-url origin >/dev/null 2>&1 || fail "origin remote is missing"
[ -x "$VENV_PYTHON" ] || fail "backend virtualenv is missing: $VENV_PYTHON"
systemctl cat "$SERVICE_NAME" >/dev/null 2>&1 || fail "systemd service is missing: $SERVICE_NAME"

SERVICE_WORKDIR="$(systemctl show "$SERVICE_NAME" -p WorkingDirectory --value 2>/dev/null || true)"
EXPECTED_WORKDIR="$ROOT_DIR/backend"
if [ -n "$SERVICE_WORKDIR" ]; then
  SERVICE_WORKDIR="$(realpath -m "$SERVICE_WORKDIR")"
  EXPECTED_WORKDIR="$(realpath -m "$EXPECTED_WORKDIR")"
  [ "$SERVICE_WORKDIR" = "$EXPECTED_WORKDIR" ] ||
    fail "$SERVICE_NAME runs from $SERVICE_WORKDIR, not this checkout; use scripts/upgrade.sh for canonical /opt/auralan installations"
fi

OLD_HEAD="$(git rev-parse HEAD)"
TMPDIR_DEPLOY="$(mktemp -d /tmp/auralan-deploy.XXXXXX)"

cleanup() {
  if git worktree list --porcelain | grep -Fq "worktree $TMPDIR_DEPLOY"; then
    git worktree remove --force "$TMPDIR_DEPLOY" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMPDIR_DEPLOY" >/dev/null 2>&1 || true
  [ -z "$READINESS_DIR" ] || rm -rf "$READINESS_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

printf 'Fetching origin/main...\n'
git fetch --prune origin main
TARGET="$(git rev-parse origin/main)"

if [ "$TARGET" = "$OLD_HEAD" ]; then
  printf 'Already up to date at %s.\n' "$(git rev-parse --short HEAD)"
  if health_json >/dev/null; then
    print_success
    exit 0
  fi

  printf 'Current code is up to date but the health endpoint is unavailable; restarting %s...\n' "$SERVICE_NAME"
  sudo systemctl restart "$SERVICE_NAME"
  printf 'Waiting for health endpoint...\n'
  wait_for_health || fail "service did not become healthy after restart"
  print_success
  exit 0
fi

git merge-base --is-ancestor "$OLD_HEAD" "$TARGET" ||
  fail "origin/main is not a fast-forward from local main"

printf 'Validating %s before deployment...\n' "$(git rev-parse --short "$TARGET")"
git worktree add --detach "$TMPDIR_DEPLOY" "$TARGET" >/dev/null
validate_tree "$TMPDIR_DEPLOY"
backup_database
check_target_state_readiness

git worktree remove --force "$TMPDIR_DEPLOY" >/dev/null
rm -rf "$TMPDIR_DEPLOY"
TMPDIR_DEPLOY=""

printf 'Fast-forwarding local main...\n'
git merge --ff-only "$TARGET"

printf 'Restarting %s...\n' "$SERVICE_NAME"
if ! sudo systemctl restart "$SERVICE_NAME"; then
  rollback_deployment "service restart failed"
fi

printf 'Waiting for health endpoint...\n'
if ! wait_for_health; then
  rollback_deployment "deployment failed health check"
fi

print_success
if [ -n "$DB_BACKUP" ]; then
  printf 'Pre-deploy database backup: %s\n' "$DB_BACKUP"
fi
