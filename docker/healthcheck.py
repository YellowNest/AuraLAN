from __future__ import annotations

import json
import os
import urllib.request


def main() -> None:
    bind = os.environ.get("AURALAN_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = os.environ.get("AURALAN_PORT", "8787").strip() or "8787"

    target = "127.0.0.1" if bind in {"0.0.0.0", "::", "[::]"} else bind
    if ":" in target and not target.startswith("["):
        target = f"[{target}]"

    with urllib.request.urlopen(
        f"http://{target}:{port}/api/v1/health",
        timeout=3,
    ) as response:
        data = json.load(response)
        if response.status != 200 or data.get("ok") is not True:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
