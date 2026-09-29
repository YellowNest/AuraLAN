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

git worktree remove --force "$TMPDIR_DEPLOY" >/dev/null
rm -rf "$TMPDIR_DEPLOY"
TMPDIR_DEPLOY=""

printf 'Fast-forwarding local main...\n'
git merge --ff-only "$TARGET"

printf 'Restarting %s...\n' "$SERVICE_NAME"
if ! sudo systemctl restart "$SERVICE_NAME"; then
  printf 'Restart failed. Rolling back to %s...\n' "$(git rev-parse --short "$OLD_HEAD")" >&2
  git reset --hard "$OLD_HEAD"
  sudo systemctl restart "$SERVICE_NAME" >/dev/null 2>&1 || true
  fail "service restart failed; previous commit restored"
fi

printf 'Waiting for health endpoint...\n'
if ! wait_for_health; then
  printf 'Health check failed. Rolling back to %s...\n' "$(git rev-parse --short "$OLD_HEAD")" >&2
  git reset --hard "$OLD_HEAD"
  if sudo systemctl restart "$SERVICE_NAME" && wait_for_health; then
    fail "deployment failed health check; previous commit restored and is healthy"
  fi
  fail "deployment failed health check; previous commit restored but service health could not be confirmed"
fi

print_success
