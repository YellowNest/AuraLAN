#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${AURALAN_HOST:-127.0.0.1}"
PORT="${AURALAN_PORT:-8787}"

cd "$ROOT_DIR/backend"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
