"""Low-level stdio MCP server exposing deterministic simulation entry points."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from typing import cast

from mcp import types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from . import __version__
from .brief import load_brief, schema
from .doctor import run_doctor
from .imports import write_import_record
from .liaison import inbox as liaison_inbox
from .liaison import ux_respond
from .records import (
    RECORDERS,
    DecisionInput,
    StageImpressionInput,
    VisionReviewInput,
    records_summary,
)
from .requests import load_request
from .responses import write_response
from .run import run_simulation
from .workspace import workspace_path, workspace_root

server = Server(f"sim-mcp/{__version__}")
ANALYSES = ("spice", "pdn", "thermal", "wca", "emc", "dft", "fem", "rf")
WRITING_TOOLS = {
    "sim_run",
    "sim_gates",
    "sim_import",
    "sim_respond",
    "sim_record_decision",
    "sim_record_impression",
    "sim_record_vision_review",
    "sim_ux_respond",
    *(f"sim_{analysis}" for analysis in ANALYSES),
}
RECORDERS_MCP = {
    "sim_record_decision": RECORDERS["decision"],
    "sim_record_impression": RECORDERS["impression"],
    "sim_record_vision_review": RECORDERS["vision-review"],
}
DESCRIPTIONS = {
    "sim_doctor": (
        "Probe the simulation tool environment (solvers, interpreters) and report "
        "what is available. Read-only; writes nothing."
    ),
    "sim_validate_brief": (
        "Validate a *.sim.json brief against the strict schema. Writes nothing."
    ),
    "sim_run": (
        "Run the brief's declared analyses and write the report bundle under "
        "out/<name>/ (sim-report.json/md, manifest, provenance, solver artifacts). "
        "Verdicts are deterministic; unknown is blocking."
    ),
    "sim_gates": (
        "Run every declared analysis and return the aggregate gate verdict, "
        "writing the same out/<name>/ report bundle. Deterministic; unknown is blocking."
    ),
    "sim_import": (
        "Validate a sibling-agent import file and record it under out/<name>/ "
        "for use by the brief. Writes an import record."
    ),
    "sim_respond": (
        "Answer a sibling *.sim-request.json: runs the requested analysis and "
        "writes <name>.sim-response.json with a deterministic status."
    ),
    "sim_schema": ("Return the JSON schema of the simulation brief. Writes nothing."),
    "sim_record_decision": (
        "Append a VibeBB decision record to observations/sim/decisions.jsonl "
        "(principles, options, evidence, risks). Advisory; never changes a verdict."
    ),
    "sim_record_impression": (
        "Append a stage impression bound to artifact hashes in "
        "observations/sim/impressions.jsonl. Advisory; never changes a verdict."
    ),
    "sim_record_vision_review": (
        "Append a vision review for an image or vision tool event to "
        "observations/sim/vision-reviews.jsonl. Advisory; never changes a verdict."
    ),
    "sim_records_status": (
        "Report record counts per log and the last Stop-hook verdict. Writes nothing."
    ),
    "sim_plots": (
        "Return inline PNG plots from an existing out/<name>/sim-report.json, "
        "verifying each sha256. Read-only; writes nothing."
    ),
    "sim_ux_inbox": (
        "List liaison/*.ux-request.json states (new/blocked/answered/stale) plus "
        "malformed files. Read-only; writes nothing."
    ),
    "sim_ux_respond": (
        "Write liaison/<id>.ux-response.json for a sim-targeted ux-request with a "
        "deterministic status. 'done' is forbidden without passing gates, "
        "artifacts, and valid record refs."
    ),
}
for _analysis in ANALYSES:
    DESCRIPTIONS[f"sim_{_analysis}"] = (
        f"Run only the {_analysis} analysis of the brief and write its results "
        "under out/<name>/. Verdicts are deterministic; unknown is blocking."
    )


def tool_specs() -> list[types.Tool]:
    schemas: dict[str, dict[str, object]] = {
        "sim_doctor": {"type": "object", "properties": {}, "additionalProperties": False},
        "sim_validate_brief": {
            "type": "object",
            "properties": {"brief": {"type": "string"}},
            "required": ["brief"],
            "additionalProperties": False,
        },
        "sim_run": {
            "type": "object",
            "properties": {
                "brief": {"type": "string"},
                "only": {"type": "array", "items": {"type": "string", "enum": list(ANALYSES)}},
                "out": {"type": "string"},
            },
            "required": ["brief"],
            "additionalProperties": False,
        },
        "sim_gates": {
            "type": "object",
            "properties": {"brief": {"type": "string"}, "out": {"type": "string"}},
            "required": ["brief"],
            "additionalProperties": False,
        },
        "sim_import": {
            "type": "object",
            "properties": {"file": {"type": "string"}, "brief": {"type": "string"}},
            "required": ["file", "brief"],
            "additionalProperties": False,
        },
        "sim_respond": {
            "type": "object",
            "properties": {"request": {"type": "string"}},
            "required": ["request"],
            "additionalProperties": False,
        },
        "sim_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "sim_plots": {
            "type": "object",
            "properties": {"out_dir": {"type": "string"}},
            "required": ["out_dir"],
            "additionalProperties": False,
        },
        "sim_ux_inbox": {"type": "object", "properties": {}, "additionalProperties": False},
        "sim_ux_respond": {
            "type": "object",
            "properties": {
                "request": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": [
                        "accepted",
                        "in_progress",
                        "done",
                        "needs_info",
                        "rejected",
                        "deferred",
                    ],
                },
                "reason": {"type": "string"},
                "questions_for_user": {"type": "array", "items": {"type": "string"}},
                "reports": {"type": "array", "items": {"type": "string"}},
                "gate_verdicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "gate": {"type": "string"},
                            "verdict": {
                                "type": "string",
                                "enum": ["pass", "fail", "unknown"],
                            },
                        },
                        "required": ["gate", "verdict"],
                        "additionalProperties": False,
                    },
                },
                "artifacts": {"type": "array", "items": {"type": "string"}},
                "decision_refs": {"type": "array", "items": {"type": "string"}},
                "impression_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["request", "status"],
            "additionalProperties": False,
        },
        "sim_record_decision": DecisionInput.model_json_schema(),
        "sim_record_impression": StageImpressionInput.model_json_schema(),
        "sim_record_vision_review": VisionReviewInput.model_json_schema(),
        "sim_records_status": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    }
    for analysis in ANALYSES:
        schemas[f"sim_{analysis}"] = {
            "type": "object",
            "properties": {"brief": {"type": "string"}, "out": {"type": "string"}},
            "required": ["brief"],
            "additionalProperties": False,
        }
    return [
        types.Tool(
            name=name,
            description=DESCRIPTIONS.get(name, name),
            inputSchema=value,
            annotations=types.ToolAnnotations(
                title=name,
                readOnlyHint=name not in WRITING_TOOLS,
                destructiveHint=False,
                idempotentHint=name not in WRITING_TOOLS,
                openWorldHint=False,
            ),
        )
        for name, value in schemas.items()
    ]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return tool_specs()


def _string_argument(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _optional_string_argument(arguments: dict[str, object], name: str) -> str | None:
    value = arguments.get(name)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _analysis_selection(arguments: dict[str, object]) -> set[str] | None:
    value = arguments.get("only")
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("only must be an array of strings")
    selection: set[str] = set()
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError("only must be an array of strings")
        selection.add(item)
    return selection or None


def dispatch_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
    root = workspace_root()
    if name == "sim_doctor":
        return {**run_doctor()[0]}
    if name == "sim_schema":
        return schema()
    if name == "sim_validate_brief":
        brief = load_brief(workspace_path(_string_argument(arguments, "brief"), root))
        return {"verdict": "pass", "name": brief.name, "schema_version": brief.schema_version}
    if name in {"sim_run", "sim_gates", *(f"sim_{x}" for x in ANALYSES)}:
        brief_path = workspace_path(_string_argument(arguments, "brief"), root)
        brief = load_brief(brief_path)
        only = (
            {name.removeprefix("sim_")}
            if name.startswith("sim_") and name not in {"sim_run", "sim_gates"}
            else _analysis_selection(arguments)
        )
        out = _optional_string_argument(arguments, "out")
        out_dir = (
            workspace_path(
                workspace_path(out, root) / brief.name,
                root,
            )
            if out
            else workspace_path(root / "out" / brief.name, root)
        )
        return {**run_simulation(brief, brief_path, root, out_dir, only)}
    if name == "sim_import":
        brief = load_brief(workspace_path(_string_argument(arguments, "brief"), root))
        return {
            "verdict": "pass",
            "import": write_import_record(
                _string_argument(arguments, "file"),
                root,
                workspace_path(root / "out" / brief.name, root),
            ),
        }
    if name in RECORDERS_MCP:
        return RECORDERS_MCP[name](arguments, root)
    if name == "sim_records_status":
        return records_summary(root)
    if name == "sim_ux_inbox":
        return liaison_inbox(root)
    if name == "sim_ux_respond":
        return ux_respond(dict(arguments), root)
    if name == "sim_plots":
        out_dir = workspace_path(_string_argument(arguments, "out_dir"), root)
        report_path = out_dir / "sim-report.json"
        if not report_path.is_file():
            raise ValueError(f"no sim-report.json under {out_dir}")
        report = cast(dict[str, object], json.loads(report_path.read_text(encoding="utf-8")))
        return {"plots": report.get("plots", []), "plot_errors": report.get("plot_errors", [])}
    if name == "sim_respond":
        request_path = workspace_path(_string_argument(arguments, "request"), root)
        request = load_request(request_path)
        try:
            brief_path = workspace_path(request.brief_path, root)
        except ValueError as exc:
            path = write_response(
                request_path,
                request.request_id,
                "needs_info",
                reasons=[f"brief path is invalid: {exc}"],
            )
            return {
                "status": "needs_info",
                "response": str(path),
                "reasons": [f"brief path is invalid: {exc}"],
            }
        if not brief_path.is_file():
            path = write_response(
                request_path,
                request.request_id,
                "needs_info",
                reasons=["brief file is missing"],
            )
            return {"status": "needs_info", "response": str(path)}
        try:
            brief = load_brief(brief_path)
        except ValueError as exc:
            path = write_response(
                request_path,
                request.request_id,
                "needs_info",
                reasons=[f"brief is invalid: {exc}"],
            )
            return {
                "status": "needs_info",
                "response": str(path),
                "reasons": [f"brief is invalid: {exc}"],
            }
        if request.kind != "any" and getattr(brief, request.kind) is None:
            path = write_response(
                request_path,
                request.request_id,
                "needs_info",
                reasons=[f"brief does not declare {request.kind}"],
            )
            return {"status": "needs_info", "response": str(path)}
        out_dir = workspace_path(root / "out" / brief.name, root)
        report = run_simulation(
            brief,
            brief_path,
            root,
            out_dir,
            {request.kind} if request.kind != "any" else None,
        )
        verdict = report["verdict"]
        status = (
            "accepted" if verdict == "pass" else "rejected" if verdict == "fail" else "needs_info"
        )
        path = write_response(
            request_path,
            request.request_id,
            status,
            verdict,
            out_dir / "sim-report.json",
            brief_path,
            [] if status != "needs_info" else ["analysis verdict is unknown"],
        )
        return {"status": status, "verdict": verdict, "response": str(path)}
    raise ValueError(f"unknown tool {name!r}")


IMAGE_TOOLS = {
    "sim_run",
    "sim_gates",
    "sim_respond",
    "sim_plots",
    *(f"sim_{analysis}" for analysis in ANALYSES),
}
MAX_PLOT_IMAGES = 8


def _payload_images(
    payload: dict[str, object], root: Path
) -> tuple[list[types.ImageContent], list[str], int]:
    """Load up to MAX_PLOT_IMAGES verified PNGs referenced by payload['plots']."""
    plots = payload.get("plots")
    images: list[types.ImageContent] = []
    mismatches: list[str] = []
    loaded = 0
    if not isinstance(plots, list):
        return images, mismatches, 0
    for item in cast(list[object], plots):
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, object], item)
        rel = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(rel, str) or not isinstance(expected, str):
            continue
        try:
            path = workspace_path(rel, root)
        except ValueError:
            mismatches.append(rel)
            continue
        if not path.is_file() or path.suffix != ".png":
            mismatches.append(rel)
            continue
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != expected:
            mismatches.append(rel)
            continue
        loaded += 1
        if len(images) < MAX_PLOT_IMAGES:
            images.append(
                types.ImageContent(
                    type="image",
                    data=base64.b64encode(blob).decode("ascii"),
                    mimeType="image/png",
                )
            )
    return images, mismatches, max(0, loaded - MAX_PLOT_IMAGES)


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
    is_error = False
    payload: dict[str, object]
    try:
        payload = dispatch_tool(name, arguments)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        payload = {"verdict": "fail", "detail": str(exc)}
        is_error = True
    images: list[types.ImageContent] = []
    if not is_error and name in IMAGE_TOOLS:
        images, mismatches, omitted = _payload_images(payload, workspace_root())
        if mismatches:
            payload["plot_hash_mismatches"] = mismatches
        if omitted:
            payload["plots_omitted"] = omitted
    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps(payload, indent=2, sort_keys=True),
            ),
            *images,
        ],
        isError=is_error,
    )


async def _serve() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=f"sim/{__version__}",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
