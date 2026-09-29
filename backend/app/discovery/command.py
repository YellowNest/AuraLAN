"""Small, bounded command runner used by discovery providers."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    code: int
    output: str
    error: str = ""


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run_command(command: list[str], timeout: float = 2.5) -> CommandResult:
    """Execute a literal argv list and decode imperfect local-tool output safely.

    Discovery tools can expose device-supplied bytes that are not valid UTF-8.
    Replacement decoding keeps one malformed hostname/TXT record from taking
    down the entire provider while shell execution remains unavailable.
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return CommandResult(result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip())
    except FileNotFoundError:
        return CommandResult(127, "", f"binary unavailable: {command[0]}")
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", f"command timed out: {command[0]}")
    except OSError as exc:
        return CommandResult(125, "", str(exc))
