"""Simulation request response writer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .workspace import reject_symlinks, workspace_root

ResponseStatus = Literal["accepted", "rejected", "deferred", "needs_info"]


class SimulationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[2] = 2
    request_id: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    brief_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: ResponseStatus
    verdict: Literal["pass", "fail", "unknown"] | None = None
    report_path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decision_refs: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_verdict(self) -> SimulationResponse:
        if self.status == "accepted" and self.verdict != "pass":
            raise ValueError("accepted responses require a pass verdict")
        if self.status == "rejected" and self.verdict != "fail":
            raise ValueError("rejected responses require a fail verdict")
        if (self.report_path is None) != (self.sha256 is None):
            raise ValueError("report_path and sha256 must be provided together")
        if self.status in ("accepted", "rejected") and self.report_path is None:
            raise ValueError("accepted and rejected responses require a hashed report")
        return self


def write_response(
    request_path: Path,
    request_id: str,
    status: ResponseStatus,
    verdict: Literal["pass", "fail", "unknown"] | None = None,
    report_path: Path | None = None,
    brief_path: Path | None = None,
    decision_refs: list[str] | None = None,
    reasons: list[str] | None = None,
) -> Path:
    if decision_refs:
        from .records import valid_event_ids

        valid = valid_event_ids(workspace_root())["decision"]
        for ref in decision_refs:
            if ref not in valid:
                raise ValueError(f"decision_ref {ref} is not a decisions.jsonl event_id")
    response = SimulationResponse(
        request_id=request_id,
        request_sha256=hashlib.sha256(request_path.read_bytes()).hexdigest(),
        brief_sha256=(
            hashlib.sha256(brief_path.read_bytes()).hexdigest()
            if brief_path is not None and brief_path.is_file()
            else None
        ),
        status=status,
        verdict=verdict,
        report_path=str(report_path) if report_path else None,
        sha256=hashlib.sha256(report_path.read_bytes()).hexdigest() if report_path else None,
        decision_refs=decision_refs or [],
        reasons=reasons or [],
    )
    stem = request_path.name.removesuffix(".sim-request.json").removesuffix(".json")
    output = request_path.with_name(stem + ".sim-response.json")
    reject_symlinks(output)
    output.write_text(
        json.dumps(response.model_dump(exclude_none=True), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
