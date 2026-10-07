"""Deterministic verdict aggregation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypedDict

Verdict = Literal["pass", "fail", "unknown"]


class GateCheckData(TypedDict):
    id: str
    analysis: str
    verdict: Verdict
    detail: str
    measured: float | None
    limit: str | None
    evidence: list[str]
    margin: float | None
    guidance: list[str]


@dataclass(frozen=True)
class GateCheck:
    id: str
    analysis: str
    verdict: Verdict
    detail: str
    measured: float | None = None
    limit: str | None = None
    evidence: list[str] | None = None
    margin: float | None = None
    guidance: list[str] | None = None

    def to_dict(self) -> GateCheckData:
        return {
            "id": self.id,
            "analysis": self.analysis,
            "verdict": self.verdict,
            "detail": self.detail,
            "measured": self.measured,
            "limit": self.limit,
            "evidence": self.evidence or [],
            "margin": self.margin,
            "guidance": self.guidance or [],
        }


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
    *,
    margin: float | None = None,
    guidance: list[str] | None = None,
) -> GateCheck:
    """``margin`` is headroom to the limit in measured units (negative = violated)."""
    if measured is not None and not math.isfinite(measured):
        return GateCheck(
            check_id, analysis, "unknown", "measurement is non-finite", evidence=evidence
        )
    if margin is not None and not math.isfinite(margin):
        margin, guidance = None, None
    return GateCheck(
        check_id, analysis, verdict, detail, measured, limit, evidence, margin, guidance
    )


def aggregate(checks: list[GateCheck]) -> Verdict:
    if any(item.verdict == "fail" for item in checks):
        return "fail"
    if not checks or any(item.verdict == "unknown" for item in checks):
        return "unknown"
    return "pass"
