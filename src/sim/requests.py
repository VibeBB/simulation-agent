"""Sister-agent simulation request schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SimulationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[1]
    from_system: Literal[
        "circuit", "mech", "wire", "bard", "firmware", "fpga", "prodeng", "dashboard", "doc", "ux"
    ]
    request_id: str = Field(min_length=1)
    kind: Literal["spice", "pdn", "thermal", "wca", "emc", "dft", "fem", "rf", "any"]
    brief_path: str = Field(min_length=1)
    question: str = Field(min_length=1)
    requested_by: str | None = None


def load_request(path: Path) -> SimulationRequest:
    try:
        return SimulationRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"could not load simulation request {path}: {exc}") from exc
