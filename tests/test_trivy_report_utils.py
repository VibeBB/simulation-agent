"""Fixtures for scripts/trivy_report_utils.py.

The gate fixture feeds a captured-style trivy JSON report through the same
aggregation the publish workflow's gate and the container audit's CIS
summary perform, including the empty-payload anomaly the audit retries on.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts import trivy_report_utils

SCRIPT = Path(__file__).parents[1] / "scripts" / "trivy_report_utils.py"


def _report(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "trivy-report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _scan_payload() -> dict[str, Any]:
    return {
        "Results": [
            {
                "Target": "ghcr.io/vibebb/sim-tools (ubuntu 26.04)",
                "Class": "os-pkgs",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-0001",
                        "PkgName": "openssl",
                        "Severity": "CRITICAL",
                        "InstalledVersion": "3.0.0",
                        "FixedVersion": "3.0.1",
                    },
                    {
                        "VulnerabilityID": "CVE-2026-0002",
                        "PkgName": "curl",
                        "Severity": "CRITICAL",
                        "InstalledVersion": "8.0.0",
                        # Unfixed: the old SARIF gate ignored it, so the
                        # python gate must ignore it too.
                    },
                    {
                        "VulnerabilityID": "CVE-2026-0003",
                        "PkgName": "zlib",
                        "Severity": "MEDIUM",
                        "InstalledVersion": "1.2.0",
                        "FixedVersion": "1.2.1",
                    },
                ],
            },
            {
                "Target": "secret-target",
                "Class": "secret",
                "Secrets": [
                    {
                        "RuleID": "private-key",
                        "Severity": "CRITICAL",
                        "Title": "Private Key",
                        "Match": "-----BEGIN",
                    }
                ],
            },
            {
                "Target": "config-target",
                "Class": "config",
                "Misconfigurations": [
                    {
                        "ID": "DS002",
                        "AVDID": "AVD-DS-0002",
                        "Title": "Image user should not be 'root'",
                        "Severity": "HIGH",
                        "Status": "FAIL",
                    }
                ],
            },
        ]
    }


def test_gate_fails_on_fixable_and_secret_and_misconfig(tmp_path: Path) -> None:
    path = _report(tmp_path, _scan_payload())
    result = _cli("gate", str(path))

    assert result.returncode == 1
    assert "CVE-2026-0001" in result.stdout
    assert "private-key" in result.stdout
    assert "AVD-DS-0002" in result.stdout
    # Unfixed CVE-2026-0002 and MEDIUM CVE-2026-0003 must not gate.
    assert "CVE-2026-0002" not in result.stdout
    assert "CVE-2026-0003" not in result.stdout
    assert "3 blocking finding(s)" in result.stdout


def test_gate_passes_on_clean_report(tmp_path: Path) -> None:
    path = _report(tmp_path, {"Results": []})
    result = _cli("gate", str(path))

    assert result.returncode == 0
    assert "0 blocking finding(s)" in result.stdout


def test_gate_passes_when_only_unfixed_or_low(tmp_path: Path) -> None:
    payload = {
        "Results": [
            {
                "Target": "image",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-0002",
                        "PkgName": "curl",
                        "Severity": "CRITICAL",
                    },
                    {
                        "VulnerabilityID": "CVE-2026-0003",
                        "PkgName": "zlib",
                        "Severity": "LOW",
                        "FixedVersion": "1.2.1",
                    },
                ],
            }
        ]
    }
    path = _report(tmp_path, payload)
    assert _cli("gate", str(path)).returncode == 0


def test_gate_counts_nested_results() -> None:
    report = {
        "Results": [
            {
                "Target": "outer",
                "Results": [
                    {
                        "Target": "inner",
                        "Secrets": [{"RuleID": "aws-key", "Severity": "HIGH", "Title": "AWS"}],
                    }
                ],
            }
        ]
    }
    rows = trivy_report_utils.gate_finding_rows(report)
    assert rows == [("secret", "aws-key", "AWS", "HIGH", "inner")]


def test_cis_aggregation_walks_nested_summaries() -> None:
    report = {
        "Results": [
            {"MisconfSummary": {"Successes": 10, "Failures": 1}},
            {
                "Results": [
                    {"MisconfSummary": {"Successes": 4, "Failures": 2}},
                    {"MisconfSummary": {"Successes": 3}},
                ]
            },
        ]
    }
    assert trivy_report_utils.cis_summary_totals(report) == {
        "passed": 17,
        "failed": 3,
    }


def test_cis_nonempty_fails_on_empty_payload(tmp_path: Path) -> None:
    # The anomaly shape the audit retries on: trivy exits 0 with an empty
    # Results payload, so the check keys on content, not the exit code.
    path = _report(tmp_path, {"Results": []})
    result = _cli("cis-nonempty", str(path))

    assert result.returncode == 1
    assert "no MisconfSummary results" in result.stderr


def test_cis_nonempty_accepts_nested_payload(tmp_path: Path) -> None:
    payload = {"Results": [{"Results": [{"MisconfSummary": {"Successes": 5, "Failures": 2}}]}]}
    path = _report(tmp_path, payload)
    assert _cli("cis-nonempty", str(path)).returncode == 0


def test_blocking_cves_renders_only_fixable_high(tmp_path: Path) -> None:
    path = _report(tmp_path, _scan_payload())
    result = _cli("blocking-cves", str(path), "sim-tools")

    assert result.returncode == 0
    assert "CVE-2026-0001" in result.stdout
    assert "1 fixable HIGH/CRITICAL finding(s)" in result.stdout
    # Secrets/misconfigs are reported by gate, not the CVE table.
    assert "private-key" not in result.stdout


def test_report_must_be_json_object(tmp_path: Path) -> None:
    path = _report(tmp_path, ["not", "an", "object"])
    result = _cli("gate", str(path))

    assert result.returncode == 1
    assert "must be a JSON object" in result.stderr


@pytest.mark.parametrize("command", ["gate", "cis-nonempty"])
def test_missing_file_fails(command: str, tmp_path: Path) -> None:
    result = _cli(command, str(tmp_path / "absent.json"))
    assert result.returncode == 1
