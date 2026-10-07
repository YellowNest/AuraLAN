from __future__ import annotations

import os
import sys


def main() -> None:
    host = os.environ.get("AURALAN_HOST", "0.0.0.0").strip() or "0.0.0.0"
    raw_port = os.environ.get("AURALAN_PORT", "8787").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("AURALAN_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("AURALAN_PORT must be between 1 and 65535")

    os.execvp(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
            "--no-access-log",
        ],
    )


if __name__ == "__main__":
    main()
