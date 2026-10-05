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


class PlotInfo(TypedDict):
    path: str
    analysis: str
    title: str
    checklist: str
    sha256: str


class SimulationReport(TypedDict):
    schema_version: int
    name: str
    verdict: Verdict
    summary: ReportSummary
    checks: list[GateCheckData]
    tools: ToolInventory
    imports: list[dict[str, object]]
    files: dict[str, object]
    plots: list[PlotInfo]
    plot_errors: list[str]


CHECKLIST_HINTS = {
    "sim-summary": "does the verdict mix match expectation?",
    "margin-chart": "which checks sit near a bound; are the units sane?",
    "spice-waveform": (
        "ringing/overshoot/settling; does the curve match the circuit "
        "intent; are measure lines on the curve?"
    ),
    "rf-sparams": "match across each band, resonances, and S21 loss",
    "dft-testpoints": "spacing, side, and coverage holes",
    "fem-deflection": "deflection shape and magnitude versus the limit",
    "intake-image": "does the attachment support the value it was cited for?",
    "sibling-render": "does the sibling render agree with the imported facts?",
}


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
    if report.get("plots") or report.get("plot_errors"):
        lines.extend(["", "## Plots", ""])
        for item in report.get("plots", []):
            relative = item["path"].split("/", 2)[-1] if "/" in item["path"] else item["path"]
            lines.append(
                f"- [{item['title']}]({relative}) — {CHECKLIST_HINTS.get(item['checklist'], '')}"
            )
        for error in report.get("plot_errors", []):
            lines.append(f"- plot not generated: {error}")
    return "\n".join(lines) + "\n"


def write_outputs(
    brief: SimulationBrief,
    brief_path: Path,
    checks: list[GateCheck],
    tools: ToolInventory,
    out_dir: Path,
    adapter_files: dict[str, object] | None = None,
    plots: list[PlotInfo] | None = None,
    plot_errors: list[str] | None = None,
) -> SimulationReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    report: SimulationReport = {
        "schema_version": 2,
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
        "plots": plots or [],
        "plot_errors": plot_errors or [],
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
