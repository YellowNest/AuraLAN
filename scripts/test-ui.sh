#!/usr/bin/env bash
# Runs in a disposable Docker container: Chromium/npm files never touch the Pi.
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
auralan_url="${AURALAN_URL:-http://127.0.0.1:8787}"

docker run --rm --network host \
  -e AURALAN_URL="$auralan_url" \
  -v "$root_dir:/app:ro" \
  node:24 bash -ceu '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq chromium >/dev/null
    ui_dir=$(mktemp -d /tmp/auralan-ui.XXXXXX)
    trap "find \"$ui_dir\" -depth -delete; rmdir \"$ui_dir\" 2>/dev/null || true" EXIT
    cp /app/scripts/ui-sanity.mjs "$ui_dir/"
    cd "$ui_dir"
    npm install --no-audit --no-fund --silent puppeteer-core
    node ui-sanity.mjs
  '
