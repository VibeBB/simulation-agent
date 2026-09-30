#!/usr/bin/env python3
"""Summarize gate status when an agent stops."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, cast


def main() -> int:
    try:
        payload: Any = json.load(sys.stdin)
        payload = cast(dict[str, Any], payload)
        root = Path(str(payload.get("working_dir") or os.getcwd())).resolve()
        reports = sorted(path for path in root.glob("out/**/sim-report.json") if path.is_file())
        entries: list[str] = []
        for path in reports:
            report = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
            checks = cast(list[dict[str, Any]], report.get("checks", []))
            failed = cast(
                list[str],
                [
                    check.get("id")
                    for check in checks
                    if check.get("verdict") in ("fail", "unknown")
                ],
            )
            entries.append(
                f"{path}: verdict={report.get('verdict')}; unresolved={', '.join(failed) or 'none'}"
            )
        context = "\n".join(entries) if entries else f"No simulation reports found under {root}."
        print(json.dumps({"decision": "allow", "additionalContext": context}))
        return 0
    except Exception as exc:
        print(f"report_sim_status: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
