#!/usr/bin/env python3
"""Deny direct writes to simulation outputs and sister responses."""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

WRITE_COMMANDS = {"tee", "rm", "mv", "cp", "install", "truncate"}


def _is_protected(value: str, root: Path) -> bool:
    candidate = Path(value.strip("'\""))
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        lexical = candidate.absolute().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    if lexical.parts and lexical.parts[0] == "out":
        return True
    if lexical.name.endswith(".sim-response.json"):
        return True
    if _is_vision_artifact(lexical):
        return True
    try:
        relative = candidate.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return (
        (relative.parts and relative.parts[0] == "out")
        or relative.name.endswith(".sim-response.json")
        or _is_vision_artifact(relative)
    )


def _is_vision_artifact(path: Path) -> bool:
    return (
        len(path.parts) >= 3
        and path.parts[:2] == ("observations", "sim")
        and path.suffix == ".jsonl"
    ) or path.parts == ("intake", "attachments", "manifest.jsonl")


PATCH_PATH_PREFIXES = (
    "*** Update File:",
    "*** Add File:",
    "*** Delete File:",
    "*** Move to:",
    "+++ b/",
    "--- a/",
)


def _file_editor_target(payload: dict[str, Any], root: Path) -> bool:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return False
    if payload.get("tool_name") in {"file_editor", "apply_patch"}:
        for key in ("path", "file_path", "filename", "target"):
            value = tool_input.get(key)
            if isinstance(value, str) and _is_protected(value, root):
                return True
        patch = tool_input.get("patch")
        if isinstance(patch, str):
            for line in patch.splitlines():
                line = line.strip()
                for prefix in PATCH_PATH_PREFIXES:
                    if line.startswith(prefix):
                        path = line.removeprefix(prefix).split("\t", 1)[0].strip()
                        if _is_protected(path, root):
                            return True
                        break
        return False
    if payload.get("tool_name") != "terminal":
        return False
    command = tool_input.get("command")
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if any(
        token in {">", ">>", "1>", "2>", "tee", "sed", "rm", "mv", "cp", "install"}
        for token in tokens
    ):
        return any(_is_protected(token, root) for token in tokens)
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid hook input: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        return 2
    event_root = (
        payload.get("working_dir") or os.environ.get("OPENHANDS_PROJECT_DIR") or os.getcwd()
    )
    root = Path(str(event_root)).resolve()
    if _file_editor_target(payload, root):
        print(
            "generated simulation outputs and *.sim-response.json files cannot be edited directly",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
