#!/usr/bin/env python3
"""session_start hook: notice pending SLP v2 ux-requests.

Stdlib only — must not import sim or pydantic. Lists
``liaison/*.ux-request.json`` files whose ``target_agent`` is ``sim`` and
which have no ``<id>.ux-response.json`` beside them, then exits 0. Any
malformed files are mentioned by count only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _root() -> Path:
    return Path(os.environ.get("OPENHANDS_PROJECT_DIR") or os.getcwd()).resolve()


def main() -> int:
    root = _root()
    directory = root / "liaison"
    pending: list[str] = []
    malformed = 0
    if directory.is_dir():
        for path in sorted(directory.glob("*.ux-request.json")):
            try:
                data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                malformed += 1
                continue
            if data.get("target_agent") != "sim":
                continue
            stem = path.name.removesuffix(".ux-request.json")
            if (directory / f"{stem}.ux-response.json").is_file():
                continue
            pending.append(stem)
    lines: list[str] = []
    if pending:
        lines.append(
            "Pending ux-creator liaison requests for sim: "
            + ", ".join(pending)
            + ". Call the sim_ux_inbox MCP tool to review them."
        )
    if malformed:
        lines.append(f"{malformed} malformed liaison request file(s) present.")
    if lines:
        print(json.dumps({"decision": "allow", "additionalContext": "\n".join(lines)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
