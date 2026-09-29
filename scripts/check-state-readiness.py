#!/usr/bin/env python3
"""Check that staged AuraLAN code can open and prepare a state directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.persistence.device_store import DeviceStore  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check-state-readiness.py DATA_DIR", file=sys.stderr)
        return 2

    data_dir = Path(sys.argv[1]).resolve()
    result = DeviceStore(data_dir).readiness_check()
    print(json.dumps({"data_dir": str(data_dir), **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
