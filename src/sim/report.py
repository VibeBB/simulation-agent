"""Auditable simulation reports, provenance, and generated-file manifest."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

from .brief import SimulationBrief
from .gates import GateCheck, GateCheckData, Verdict, aggregate
from .tools import ToolInventory

ReportSummary = TypedDict(
    "ReportSummary",
    {"pass": int, "fail": int, "unknown": int},
)


class SimulationReport(TypedDict):
    schema_version: int
    name: str
    verdict: Verdict
    summary: ReportSummary
    checks: list[GateCheckData]
    tools: ToolInventory
    imports: list[dict[str, object]]
    files: dict[str, object]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_markdown(report: SimulationReport) -> str:
    lines = [
        f"# Simulation report: {report['name']}",
        "",
        f"**verdict: {report['verdict']}**",
        "",
        "## Checks",
        "",
        "| Gate | Verdict | Detail |",
        "| --- | --- | --- |",
    ]
    for item in report["checks"]:
        detail = str(item["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{item['id']}` | {item['verdict']} | {detail} |")
    lines.extend(["", "## Tools", ""])
    for name, data in report.get("tools", {}).items():
        status = "available" if data["available"] else "missing"
        lines.append(
            f"- {name}: {status} ({data.get('version') or data.get('detail') or 'unknown'})"
        )
    return "\n".join(lines) + "\n"


def write_outputs(
    brief: SimulationBrief,
    brief_path: Path,
    checks: list[GateCheck],
    tools: ToolInventory,
    out_dir: Path,
    adapter_files: dict[str, object] | None = None,
) -> SimulationReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    report: SimulationReport = {
        "schema_version": 1,
        "name": brief.name,
        "verdict": aggregate(checks),
        "summary": {
            "pass": sum(item.verdict == "pass" for item in checks),
            "fail": sum(item.verdict == "fail" for item in checks),
            "unknown": sum(item.verdict == "unknown" for item in checks),
        },
        "checks": [item.to_dict() for item in checks],
        "tools": tools,
        "imports": [],
        "files": adapter_files or {},
    }
    imports_path = out_dir / "imports.json"
    if not imports_path.is_file():
        imports_path.write_text("[]\n", encoding="utf-8")
    if imports_path.is_file():
        imported_records = cast(object, json.loads(imports_path.read_text(encoding="utf-8")))
        if not isinstance(imported_records, list):
            raise ValueError("imports.json must contain an array of objects")
        records = cast(list[object], imported_records)
        if not all(isinstance(item, dict) for item in records):
            raise ValueError("imports.json must contain an array of objects")
        report["imports"] = [cast(dict[str, object], item) for item in records]
    report_json = out_dir / "sim-report.json"
    report_md = out_dir / "sim-report.md"
    report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_md.write_text(render_markdown(report), encoding="utf-8")
    provenance = {
        "schema_version": 1,
        "brief_path": str(brief_path),
        "brief_sha256": sha256_file(brief_path),
        "imports": report["imports"],
        "tool_versions": {name: value.get("version") for name, value in tools.items()},
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    provenance_path = out_dir / "provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "files": {
            str(path.relative_to(out_dir)): sha256_file(path)
            for path in sorted(out_dir.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
