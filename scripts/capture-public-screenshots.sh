#!/usr/bin/env bash
# Generate publishable AuraLAN UI screenshots without installing Node/Chromium on the host.
root_dir="$(cd "$(dirname "$0")/.." && pwd)" || exit 1
auralan_url="${AURALAN_URL:-http://127.0.0.1:8787}"
output_dir="$root_dir/site/screenshots"

command -v docker >/dev/null 2>&1 || {
  echo "STOPP: Docker saknas."
  exit 1
}

curl -fsS "$auralan_url/api/v1/health" >/dev/null 2>&1 || {
  echo "STOPP: AuraLAN svarar inte på $auralan_url"
  exit 1
}

mkdir -p "$output_dir" || exit 1
rm -f "$output_dir"/*.png

docker run --rm --network host \
  -e AURALAN_URL="$auralan_url" \
  -e AURALAN_REPO_ROOT=/app \
  -e AURALAN_PUBLIC_SCREENSHOTS=/output \
  -v "$root_dir:/app:ro" \
  -v "$output_dir:/output" \
  node:24 bash -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq || exit 1
    apt-get install -y -qq chromium >/dev/null || exit 1
    ui_dir=$(mktemp -d /tmp/auralan-public-ui.XXXXXX) || exit 1
    cp /app/scripts/capture-public-screenshots.mjs "$ui_dir/" || exit 1
    cd "$ui_dir" || exit 1
    npm install --no-audit --no-fund --silent puppeteer-core || exit 1
    node capture-public-screenshots.mjs || exit 1
  ' || exit 1

expected="overview-desktop-dark.png network-desktop-dark.png devices-desktop-dark.png activity-desktop-dark.png overview-mobile-dark.png"
for file in $expected; do
  [ -s "$output_dir/$file" ] || {
    echo "STOPP: saknar $file"
    exit 1
  }
done

echo
echo "Public screenshots klara:"
ls -lh "$output_dir"/*.png
