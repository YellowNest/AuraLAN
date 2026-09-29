#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT_DIR/backend/.venv"
PORT="${AURALAN_CHECK_PORT:-8878}"
TMP_STATE="$(mktemp -d /tmp/auralan-local-check.XXXXXX)"
SERVER_LOG="$TMP_STATE/server.log"
SERVER_PID=""

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_STATE"
}
trap cleanup EXIT

cd "$ROOT_DIR"

command -v git >/dev/null 2>&1 || fail "git is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

[ "$(git branch --show-current)" = "main" ] || fail "local release check must run from main"
[ -z "$(git status --porcelain)" ] || fail "working tree is not clean"

printf 'Checking that local main matches origin/main...\n'
git fetch --prune origin main
LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse origin/main)"
[ "$LOCAL_HEAD" = "$REMOTE_HEAD" ] || fail "local main is not exactly origin/main"

printf '\n[1/7] Repository hygiene\n'
python3 scripts/validate-release.py
python3 scripts/audit-history.py

printf '\n[2/7] Python environment\n'
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r backend/requirements.txt
"$VENV/bin/python" -m pip check
"$VENV/bin/python" -m compileall -q backend/app

printf '\n[3/7] Backend tests\n'
(
  cd backend
  "$VENV/bin/python" -m unittest discover -s tests -v
)

printf '\n[4/7] Frontend tests\n'
if command -v node >/dev/null 2>&1; then
  while IFS= read -r -d '' source; do
    node --check "$source"
  done < <(find frontend scripts -type f \( -name '*.js' -o -name '*.mjs' \) -print0)
  node --test frontend/tests/*.test.mjs
else
  printf 'Node is not installed; frontend Node tests skipped.\n'
fi

printf '\n[5/7] Isolated HTTP smoke test on 127.0.0.1:%s\n' "$PORT"
AURALAN_DATA_DIR="$TMP_STATE/state"   "$VENV/bin/uvicorn" app.main:app   --app-dir backend   --host 127.0.0.1   --port "$PORT"   >"$SERVER_LOG" 2>&1 &
SERVER_PID="$!"

healthy=0
for _ in {1..20}; do
  if "$VENV/bin/python" - "$PORT" <<'PY' >/dev/null 2>&1
import json
import sys
import urllib.request

port = sys.argv[1]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1) as response:
    payload = json.load(response)
    raise SystemExit(0 if response.status == 200 and payload.get("ok") is True else 1)
PY
  then
    healthy=1
    break
  fi
  sleep 0.5
done

if [ "$healthy" -ne 1 ]; then
  cat "$SERVER_LOG" >&2 || true
  fail "isolated AuraLAN instance did not become healthy"
fi

"$VENV/bin/python" - "$PORT" <<'PY'
import json
import sys
import urllib.request

port = sys.argv[1]
base = f"http://127.0.0.1:{port}"

for path in ("/", "/manifest.webmanifest", "/api/v1/meta", "/api/v1/status", "/api/v1/devices", "/api/v1/monitor", "/api/v1/notifications", "/metrics"):
    with urllib.request.urlopen(base + path, timeout=5) as response:
        if response.status != 200:
            raise SystemExit(f"{path}: HTTP {response.status}")

with urllib.request.urlopen(base + "/api/v1/status", timeout=5) as response:
    status = json.load(response)
print(
    "HTTP smoke OK — "
    f"system={status.get('system', {}).get('state', 'unknown')} "
    f"devices={len(status.get('devices', []))}"
)
PY

kill "$SERVER_PID" >/dev/null 2>&1 || true
wait "$SERVER_PID" >/dev/null 2>&1 || true
SERVER_PID=""

printf '\n[6/7] Fresh device-identification audit\n'
"$VENV/bin/python" scripts/device-audit.py

printf '\n[7/7] Git state\n'
printf 'Branch: %s\n' "$(git branch --show-current)"
printf 'Commit: %s\n' "$(git rev-parse HEAD)"
printf 'Origin: %s\n' "$(git remote get-url origin)"
printf '\nAuraLAN local release check completed successfully.\n'
