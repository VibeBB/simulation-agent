"""Deterministic verdict aggregation."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

Verdict = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class GateCheck:
    id: str
    analysis: str
    verdict: Verdict
    detail: str
    measured: float | None = None
    limit: str | None = None
    evidence: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["evidence"] = self.evidence or []
        return value


@dataclass(frozen=True)
class GateReport:
    name: str
    verdict: Verdict
    checks: list[GateCheck]
    tools: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "name": self.name,
            "verdict": self.verdict,
            "summary": {
                status: sum(check.verdict == status for check in self.checks)
                for status in ("pass", "fail", "unknown")
            },
            "checks": [check.to_dict() for check in self.checks],
            "tools": self.tools,
        }


def check(
    check_id: str,
    analysis: str,
    verdict: Verdict,
    detail: str,
    measured: float | None = None,
    limit: str | None = None,
    evidence: list[str] | None = None,
) -> GateCheck:
    if measured is not None and not math.isfinite(measured):
        return GateCheck(
            check_id, analysis, "unknown", "measurement is non-finite", evidence=evidence
        )
    return GateCheck(check_id, analysis, verdict, detail, measured, limit, evidence)


def aggregate(checks: list[GateCheck]) -> Verdict:
    if any(item.verdict == "fail" for item in checks):
        return "fail"
    if not checks or any(item.verdict == "unknown" for item in checks):
        return "unknown"
    return "pass"
