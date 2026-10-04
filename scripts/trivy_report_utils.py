#!/usr/bin/env python3
"""Shared Trivy report helpers for the publish and container-audit workflows.

Commands:

    gate REPORT
        Exit 1 when the JSON report contains findings that block publish:
        fixable HIGH/CRITICAL vulnerabilities, any HIGH/CRITICAL secret, or
        any HIGH/CRITICAL misconfiguration — the same set the former SARIF
        scan's severity/ignore-unfixed filters gated on. Prints the
        offending findings as a markdown table for GITHUB_STEP_SUMMARY.
    blocking-cves REPORT TITLE
        Render just the fixable HIGH/CRITICAL vulnerability table.
    cis-nonempty REPORT
        Exit 0 only when a --compliance JSON report contains at least one
        MisconfSummary payload. Trivy exits 0 on the empty-results anomaly,
        so the container-audit retry keys on content, not the exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

_GATE_SEVERITIES = ("HIGH", "CRITICAL")


def iter_results(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield the node and every nested Results entry (compliance reports nest)."""
    yield node
    for child in cast(list[Any], node.get("Results") or []):
        if isinstance(child, dict):
            yield from iter_results(cast(dict[str, Any], child))


def blocking_cve_rows(report: dict[str, Any]) -> list[tuple[str, ...]]:
    """(CVE, package, severity, installed, fixed, target) rows that gate a publish."""
    rows: list[tuple[str, ...]] = []
    for result in iter_results(report):
        target = str(result.get("Target", "?"))
        for vuln_any in cast(list[Any], result.get("Vulnerabilities") or []):
            if not isinstance(vuln_any, dict):
                continue
            vuln = cast(dict[str, Any], vuln_any)
            if vuln.get("Severity") in _GATE_SEVERITIES and vuln.get("FixedVersion"):
                rows.append(
                    (
                        str(vuln["VulnerabilityID"]),
                        str(vuln.get("PkgName", "?")),
                        str(vuln["Severity"]),
                        str(vuln.get("InstalledVersion", "?")),
                        str(vuln["FixedVersion"]),
                        target,
                    )
                )
    return rows


def gate_finding_rows(report: dict[str, Any]) -> list[tuple[str, ...]]:
    """(Kind, ID, Detail, Severity, Target) rows that reproduce the SARIF gate.

    The retired SARIF scan gated on every HIGH/CRITICAL result across the
    vuln/secret/misconfig scanners, with unfixed vulnerabilities excluded.
    """
    rows: list[tuple[str, ...]] = []
    for result in iter_results(report):
        target = str(result.get("Target", "?"))
        for vuln_any in cast(list[Any], result.get("Vulnerabilities") or []):
            if not isinstance(vuln_any, dict):
                continue
            vuln = cast(dict[str, Any], vuln_any)
            if vuln.get("Severity") in _GATE_SEVERITIES and vuln.get("FixedVersion"):
                detail = (
                    f"{vuln.get('PkgName', '?')} "
                    f"{vuln.get('InstalledVersion', '?')} -> {vuln['FixedVersion']}"
                )
                rows.append(
                    (
                        "vuln",
                        str(vuln["VulnerabilityID"]),
                        detail,
                        str(vuln["Severity"]),
                        target,
                    )
                )
        for secret_any in cast(list[Any], result.get("Secrets") or []):
            if not isinstance(secret_any, dict):
                continue
            secret = cast(dict[str, Any], secret_any)
            if secret.get("Severity") in _GATE_SEVERITIES:
                rows.append(
                    (
                        "secret",
                        str(secret.get("RuleID", "?")),
                        str(secret.get("Title") or secret.get("Match", "?")),
                        str(secret["Severity"]),
                        target,
                    )
                )
        for mis_any in cast(list[Any], result.get("Misconfigurations") or []):
            if not isinstance(mis_any, dict):
                continue
            mis = cast(dict[str, Any], mis_any)
            if mis.get("Severity") in _GATE_SEVERITIES:
                rows.append(
                    (
                        "misconfig",
                        str(mis.get("AVDID") or mis.get("ID", "?")),
                        str(mis.get("Title", "?")),
                        str(mis["Severity"]),
                        target,
                    )
                )
    return rows


def render_blocking_table(title: str, rows: list[tuple[str, ...]]) -> str:
    lines = [
        f"## Blocking {title} findings",
        "",
        "| CVE | Package | Severity | Installed | Fixed | Target |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in sorted(rows))
    lines.append(f"\n{len(rows)} fixable HIGH/CRITICAL finding(s)")
    return "\n".join(lines) + "\n"


def render_gate_table(rows: list[tuple[str, ...]]) -> str:
    lines = [
        "## Trivy gate findings",
        "",
        "| Kind | ID | Detail | Severity | Target |",
        "|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in sorted(rows))
    lines.append(f"\n{len(rows)} blocking finding(s)")
    return "\n".join(lines) + "\n"


def cis_summary_totals(report: dict[str, Any]) -> dict[str, int]:
    """Sum MisconfSummary Successes/Failures across nested Results nodes."""
    passed = failed = 0
    for result in iter_results(report):
        summary = result.get("MisconfSummary")
        if not isinstance(summary, dict):
            continue
        totals = cast(dict[str, Any], summary)
        passed += int(totals.get("Successes", 0))
        failed += int(totals.get("Failures", 0))
    return {"passed": passed, "failed": failed}


def _load_report(path: Path) -> dict[str, Any]:
    report: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError(f"trivy report must be a JSON object: {path}")
    return cast(dict[str, Any], report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    gate = subparsers.add_parser("gate")
    gate.add_argument("report", type=Path)
    blocking = subparsers.add_parser("blocking-cves")
    blocking.add_argument("report", type=Path)
    blocking.add_argument("title")
    cis = subparsers.add_parser("cis-nonempty")
    cis.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = _load_report(args.report)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.command == "blocking-cves":
        print(render_blocking_table(args.title, blocking_cve_rows(report)), end="")
        return 0
    if args.command == "cis-nonempty":
        totals = cis_summary_totals(report)
        if totals["passed"] + totals["failed"] == 0:
            print(f"{args.report}: no MisconfSummary results", file=sys.stderr)
            return 1
        return 0
    rows = gate_finding_rows(report)
    print(render_gate_table(rows), end="")
    return 1 if rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
