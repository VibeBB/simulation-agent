"""Low-level stdio MCP server exposing deterministic simulation entry points."""

from __future__ import annotations

import asyncio
import json
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
    *(f"sim_{analysis}" for analysis in ANALYSES),
}


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
            description=name.replace("_", " "),
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
            [] if status != "needs_info" else ["analysis verdict is unknown"],
        )
        return {"status": status, "verdict": verdict, "response": str(path)}
    raise ValueError(f"unknown tool {name!r}")


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
    is_error = False
    try:
        payload = dispatch_tool(name, arguments)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        payload = {"verdict": "fail", "detail": str(exc)}
        is_error = True
    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps(payload, indent=2, sort_keys=True),
            )
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
