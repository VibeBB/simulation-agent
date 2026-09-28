#!/usr/bin/env python3
"""Block a small set of unambiguous dangerous terminal commands."""

from __future__ import annotations

import json
import re
import shlex
import sys
from typing import Any


def evaluate(command: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    lowered = [token.lower() for token in tokens]
    if any(
        token in {"reboot", "shutdown", "poweroff", "mkfs", "fdisk", "wipefs"} for token in lowered
    ):
        return "dangerous system command"
    if re.search(r"\brm\s+-(?:[a-z]*r[a-z]*f|[a-z]*f[a-z]*r)\s+/(?:\s|$)", command):
        return "recursive forced removal of root is denied"
    for index, token in enumerate(lowered):
        if token == "git" and index + 1 < len(lowered):
            operation = lowered[index + 1]
            rest = lowered[index + 2 :]
            if operation == "push" and ({"main", "master"} & set(rest)):
                return "pushing to main/master is denied"
            if operation == "reset" and "--hard" in rest:
                return "git reset --hard is denied"
            if operation == "clean" and any(flag.startswith("-") and "f" in flag for flag in rest):
                return "git clean -f is denied"
            if operation == "add" and any(item in {".", "-A", "--all"} for item in rest):
                return "git add . / -A is denied"
            if operation == "commit" and any(item in {"--amend", "--no-verify"} for item in rest):
                return "git commit --amend / --no-verify is denied"
    return None


def main() -> int:
    try:
        payload: Any = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid hook input: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict) or payload.get("tool_name") != "terminal":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or not isinstance(tool_input.get("command"), str):
        return 0
    denied = evaluate(tool_input["command"])
    if denied:
        print(f"safety rail: {denied}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
