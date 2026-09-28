"""Tool availability probe."""

from __future__ import annotations

import os
from typing import Any

from .tools import discover_tools


def run_doctor(strict: bool = False) -> tuple[dict[str, Any], int]:
    tools = discover_tools()
    required = {
        item.strip()
        for item in os.environ.get("SIM_REQUIRED_TOOLS", "ngspice,ccx,openems,kicad_rfsim").split(
            ","
        )
        if item.strip()
    }
    missing = sorted(name for name in required if name not in tools or not tools[name]["available"])
    report = {
        "schema_version": 1,
        "verdict": "fail" if strict and missing else "pass",
        "tools": tools,
        "missing": missing,
    }
    return report, 1 if strict and missing else 0
