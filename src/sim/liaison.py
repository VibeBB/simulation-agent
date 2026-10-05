"""SLP v2 liaison protocol: ux-request inbox and ux-response writer.

Requests live in the flat workspace directory ``liaison/`` as
``<id>.ux-request.json``; the deterministic ``ux_respond`` entry point is
the only writer of ``<id>.ux-response.json`` files.
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .records import records_dir, sha256_file, tree_sha256
from .workspace import reject_symlinks, workspace_path, workspace_root

SCHEMA_VERSION = 2
SYSTEM = "ux-creator"
RESPONDER = "sim"
LIAISON_DIR = "liaison"
_SLUG = r"^[a-z0-9][a-z0-9-]{2,63}$"
_SHA256 = r"^[0-9a-f]{64}$"
_JOB_ID = re.compile(r"\b(?:UX-JOB|ux-job)-[A-Za-z0-9-]+\b")
STAGES = (
    "requirements",
    "design",
    "manufacturing_handoff",
    "build",
    "evaluation",
    "revision",
)
STATUSES = ("accepted", "in_progress", "done", "needs_info", "rejected", "deferred")
_REASON_REQUIRED = {"done", "needs_info", "rejected", "deferred"}
_STATE_ORDER = ("stale", "answered", "blocked", "new")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InputRef(_Strict):
    path: str = Field(min_length=1, description="Workspace-relative input path")
    sha256: str = Field(pattern=_SHA256)


class ArtifactRef(_Strict):
    path: str = Field(min_length=1, description="Workspace-relative artifact path")
    sha256: str = Field(pattern=_SHA256)


class GateVerdict(_Strict):
    gate: str = Field(min_length=1)
    verdict: Literal["pass", "fail", "unknown"]


class UXRequest(_Strict):
    schema_version: Literal[2] = SCHEMA_VERSION
    system: Literal["ux-creator"] = SYSTEM
    id: str = Field(pattern=_SLUG)
    target_agent: str = Field(min_length=1)
    stage: Literal[
        "requirements", "design", "manufacturing_handoff", "build", "evaluation", "revision"
    ]
    risk: Literal["low", "high"]
    purpose: str = Field(min_length=10)
    rationale: str = Field(min_length=20)
    requested_changes: list[str] = Field(min_length=1)
    inputs: list[InputRef] = Field(default_factory=lambda: list[InputRef]())
    expected_deliverables: list[str] = Field(min_length=1)
    acceptance: list[str] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    created_at: AwareDatetime

    @field_validator("requested_changes")
    @classmethod
    def _changes_non_empty(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("requested_changes entries must be non-empty")
        return value

    @field_validator("depends_on")
    @classmethod
    def _deps_are_slugs(cls, value: list[str]) -> list[str]:
        for item in value:
            if re.fullmatch(_SLUG[1:-1], item) is None:
                raise ValueError(f"depends_on id {item!r} is not a slug")
        return value

    @field_validator("rationale")
    @classmethod
    def _high_risk_cites_job(cls, value: str) -> str:
        return value

    @property
    def job_id_ok(self) -> bool:
        return self.risk != "high" or _JOB_ID.search(self.rationale) is not None


class UXResponse(_Strict):
    schema_version: Literal[2] = SCHEMA_VERSION
    system: Literal["ux-creator"] = SYSTEM
    request: str = Field(pattern=_SLUG)
    responder: Literal["sim"] = RESPONDER
    status: Literal["accepted", "in_progress", "done", "needs_info", "rejected", "deferred"]
    reason: str = ""
    input_hashes: dict[str, str] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=lambda: list[ArtifactRef]())
    gate_verdicts: list[GateVerdict] = Field(default_factory=lambda: list[GateVerdict]())
    decision_refs: list[str] = Field(default_factory=list)
    impression_refs: list[str] = Field(default_factory=list)
    questions_for_user: list[str] = Field(default_factory=list)
    responded_at: AwareDatetime


def liaison_dir(root: Path) -> Path:
    return root / LIAISON_DIR


def _stem(path: Path) -> str:
    return path.name.removesuffix(".ux-request.json")


def request_path(root: Path, request_id: str) -> Path:
    return liaison_dir(root) / f"{request_id}.ux-request.json"


def response_path(root: Path, request_id: str) -> Path:
    return liaison_dir(root) / f"{request_id}.ux-response.json"


def load_request(path: Path) -> UXRequest:
    """Validate an ux-request file, including the id == file stem rule."""
    request = UXRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if request.id != _stem(path):
        raise ValueError(f"request id {request.id!r} != file stem {_stem(path)!r}")
    if not request.job_id_ok:
        raise ValueError("high-risk requests must cite a UX job id in the rationale")
    return request


def _load_response(path: Path) -> UXResponse | None:
    try:
        response = UXResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return response


def _input_hash(entry: InputRef, root: Path) -> tuple[str | None, str | None]:
    """Return (current hash, problem) for one declared input."""
    try:
        path = workspace_path(entry.path, root)
    except ValueError:
        return None, f"input {entry.path} escapes the workspace"
    if not path.exists() or path.is_symlink():
        return None, f"input {entry.path} is missing"
    current = tree_sha256(path)
    if current != entry.sha256:
        return current, f"input {entry.path} changed since the request"
    return current, None


def event_ids(directory: Path, filename: str) -> set[str]:
    path = directory / filename
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = cast(object, json.loads(line))
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            event_id = cast(dict[str, object], record).get("event_id")
            if isinstance(event_id, str):
                ids.add(event_id)
    return ids


def _hash_artifact(value: str, root: Path) -> ArtifactRef:
    path = workspace_path(value, root)
    if path.is_symlink() or any(part.is_symlink() for part in path.parents if part != path):
        raise ValueError(f"artifact is behind a symlink: {value}")
    if not path.exists():
        raise ValueError(f"artifact does not exist: {value}")
    relative = path.relative_to(root.resolve()).as_posix()
    return ArtifactRef(path=relative, sha256=tree_sha256(path))


def _report_verdicts(value: str, root: Path) -> tuple[list[GateVerdict], ArtifactRef]:
    path = workspace_path(value, root)
    if path.is_symlink():
        raise ValueError(f"report path is a symlink: {value}")
    if not path.is_file():
        raise ValueError(f"report does not exist: {value}")
    report = cast(object, json.loads(path.read_text(encoding="utf-8")))
    checks = cast(dict[str, object], report).get("checks")
    if not isinstance(checks, list):
        raise ValueError(f"{value} has no checks list")
    verdicts: list[GateVerdict] = []
    for item in cast(list[object], checks):
        if not isinstance(item, dict) or "id" not in item or "verdict" not in item:
            raise ValueError(f"{value} contains a malformed check entry")
        entry = cast(dict[str, object], item)
        verdicts.append(
            GateVerdict(
                gate=str(entry["id"]),
                verdict=cast(Literal["pass", "fail", "unknown"], entry["verdict"]),
            )
        )
    relative = path.relative_to(root.resolve()).as_posix()
    return verdicts, ArtifactRef(path=relative, sha256=sha256_file(path))


def ux_respond(payload: dict[str, object], root: Path | None = None) -> dict[str, object]:
    """Write <id>.ux-response.json for a sim-targeted request. Atomic overwrite."""
    base = (root or workspace_root()).resolve()
    request_value = payload.get("request")
    if not isinstance(request_value, str):
        raise ValueError("request must name the ux-request file or id")
    path = (
        workspace_path(request_value, base)
        if request_value.endswith(".json") or "/" in request_value
        else request_path(base, request_value)
    )
    request = load_request(path)
    if request.target_agent != RESPONDER:
        raise ValueError(f"request targets {request.target_agent!r}, not sim")

    status = payload.get("status")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        raise ValueError("reason must be a string")
    if status in _REASON_REQUIRED and len(reason) < 20:
        raise ValueError(f"status {status} requires a reason of at least 20 characters")
    questions_raw = cast(list[object], payload.get("questions_for_user") or [])
    if not all(isinstance(q, str) for q in questions_raw):
        raise ValueError("questions_for_user must be a list of strings")
    questions = [q for q in questions_raw if isinstance(q, str)]
    if status == "needs_info" and not questions:
        raise ValueError("needs_info requires at least one question_for_user")

    input_hashes: dict[str, str] = {}
    input_problems: list[str] = []
    for entry in request.inputs:
        current, problem = _input_hash(entry, base)
        if current is not None:
            input_hashes[entry.path] = current
        if problem is not None:
            input_problems.append(problem)

    gate_verdicts: list[GateVerdict] = []
    artifacts: list[ArtifactRef] = []
    report_values = cast(list[object], payload.get("reports") or [])
    for report_value in report_values:
        if not isinstance(report_value, str):
            raise ValueError("reports entries must be paths")
        verdicts, artifact = _report_verdicts(report_value, base)
        gate_verdicts.extend(verdicts)
        artifacts.append(artifact)
    for value in cast(list[object], payload.get("gate_verdicts") or []):
        gate_verdicts.append(GateVerdict.model_validate(value))
    for value in cast(list[object], payload.get("artifacts") or []):
        if not isinstance(value, str):
            raise ValueError("artifacts entries must be workspace-relative paths")
        artifacts.append(_hash_artifact(value, base))

    decision_raw = cast(list[object], payload.get("decision_refs") or [])
    impression_raw = cast(list[object], payload.get("impression_refs") or [])
    if not all(isinstance(item, str) for item in decision_raw):
        raise ValueError("decision_refs must be a list of event_id strings")
    if not all(isinstance(item, str) for item in impression_raw):
        raise ValueError("impression_refs must be a list of event_id strings")
    decision_refs = [item for item in decision_raw if isinstance(item, str)]
    impression_refs = [item for item in impression_raw if isinstance(item, str)]
    directory = records_dir(base)
    decision_ids = event_ids(directory, "decisions.jsonl")
    impression_ids = event_ids(directory, "impressions.jsonl") | event_ids(
        directory, "vision-reviews.jsonl"
    )
    for ref in decision_refs:
        if ref not in decision_ids:
            raise ValueError(f"decision_ref {ref} is not a decisions.jsonl event_id")
    for ref in impression_refs:
        if ref not in impression_ids:
            raise ValueError(f"impression_ref {ref} is not an impressions/vision-reviews event_id")

    if status == "done":
        problems = list(input_problems)
        if not gate_verdicts:
            problems.append("done requires gate_verdicts")
        if not artifacts:
            problems.append("done requires artifacts")
        if not decision_refs:
            problems.append("done requires decision_refs")
        if not impression_refs:
            problems.append("done requires impression_refs")
        blocking = [item.gate for item in gate_verdicts if item.verdict != "pass"]
        if blocking:
            problems.append(f"done is forbidden with non-pass gates: {', '.join(blocking)}")
        if problems:
            raise ValueError("; ".join(problems))

    response = UXResponse(
        request=request.id,
        status=status,
        reason=reason,
        input_hashes=input_hashes,
        artifacts=artifacts,
        gate_verdicts=gate_verdicts,
        decision_refs=decision_refs,
        impression_refs=impression_refs,
        questions_for_user=questions,
        responded_at=datetime.now(UTC),
    )
    target = response_path(base, request.id)
    reject_symlinks(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = response.model_dump_json(indent=2)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=target.parent, delete=False, encoding="utf-8", suffix=".tmp"
    ) as stream:
        stream.write(rendered + "\n")
        temp = Path(stream.name)
    temp.replace(target)
    return {
        "verdict": "pass",
        "status": status,
        "response": str(target),
        "request": request.id,
    }


def _request_state(
    path: Path, request: UXRequest, root: Path, answered_ids: set[str]
) -> tuple[str, list[str], str | None]:
    problems: list[str] = []
    response = _load_response(response_path(root, request.id))
    answered = response is not None and response.request == request.id
    stale = False
    for entry in request.inputs:
        current, problem = _input_hash(entry, root)
        if problem is not None:
            problems.append(problem)
            stale = True
        elif answered and response is not None:
            if response.input_hashes.get(entry.path) != current:
                problems.append(f"input {entry.path} changed since the response")
                stale = True
    if stale:
        return "stale", problems, response.status if response else None
    if answered:
        return "answered", problems, cast(UXResponse, response).status
    for dep in request.depends_on:
        dep_response = _load_response(response_path(root, dep))
        dep_answered = dep_response is not None and dep_response.request == dep
        if not dep_answered:
            problems.append(f"depends_on {dep} has no valid response")
    if problems:
        return "blocked", problems, None
    return "new", problems, None


def inbox(root: Path | None = None) -> dict[str, object]:
    """Project liaison/*.ux-request.json into per-request states."""
    base = (root or workspace_root()).resolve()
    directory = liaison_dir(base)
    requests: list[dict[str, object]] = []
    malformed: list[dict[str, str]] = []
    answered_ids = {
        path.name.removesuffix(".ux-response.json") for path in directory.glob("*.ux-response.json")
    }
    for path in sorted(directory.glob("*.ux-request.json")) if directory.is_dir() else []:
        try:
            request = load_request(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            malformed.append({"path": str(path), "error": str(exc)})
            continue
        if request.target_agent != RESPONDER:
            continue
        state, problems, response_status = _request_state(path, request, base, answered_ids)
        requests.append(
            {
                "id": request.id,
                "path": str(path),
                "stage": request.stage,
                "risk": request.risk,
                "purpose": request.purpose,
                "depends_on": request.depends_on,
                "state": state,
                "problems": problems,
                "response": response_status,
            }
        )
    requests.sort(key=lambda item: (_STATE_ORDER.index(str(item["state"])), str(item["id"])))
    return {"requests": requests, "malformed": malformed}
