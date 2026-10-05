"""Command-line interface for simulation-agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NoReturn, cast

from .brief import load_brief, schema
from .doctor import run_doctor
from .imports import write_import_record
from .records import RECORDERS, records_summary
from .report import sha256_file
from .requests import load_request
from .responses import write_response
from .run import run_simulation
from .workspace import workspace_path, workspace_root


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        _print({"verdict": "fail", "detail": message})
        raise SystemExit(2)


def _parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="sim")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--strict", action="store_true")
    doctor.add_argument("--warn", action="store_true")
    validate = subparsers.add_parser("validate")
    validate.add_argument("brief")
    for command in ("run", "gates"):
        item = subparsers.add_parser(command)
        item.add_argument("brief")
        item.add_argument("--only", default=None)
        item.add_argument("--out", default=None)
    report = subparsers.add_parser("report")
    report.add_argument("outdir")
    plots = subparsers.add_parser("plots")
    plots.add_argument("outdir")
    do_import = subparsers.add_parser("import")
    do_import.add_argument("file")
    do_import.add_argument("--brief", required=True)
    respond = subparsers.add_parser("respond")
    respond.add_argument("request")
    record = subparsers.add_parser("record")
    record_sub = record.add_subparsers(dest="record_kind", required=True)
    for kind in ("decision", "impression", "vision-review"):
        item = record_sub.add_parser(kind)
        item.add_argument("--json", required=True)
    record_sub.add_parser("status")
    subparsers.add_parser("schema")
    return parser


def _run_command(args: argparse.Namespace, root: Path) -> int:
    brief_path = workspace_path(args.brief, root)
    brief = load_brief(brief_path)
    out_base = workspace_path(args.out, root) if args.out else root / "out"
    out_dir = workspace_path(out_base / brief.name, root)
    only = {item for item in args.only.split(",") if item} if args.only else None
    report = run_simulation(brief, brief_path, root, out_dir, only)
    _print(report)
    return {"pass": 0, "fail": 1, "unknown": 3}[report["verdict"]]


def _respond(args: argparse.Namespace, root: Path) -> int:
    request_path = workspace_path(args.request, root)
    request = load_request(request_path)
    reasons: list[str] = []
    try:
        brief_path = workspace_path(request.brief_path, root)
    except ValueError as exc:
        reasons.append(f"brief path is invalid: {exc}")
        response = write_response(
            request_path,
            request.request_id,
            "needs_info",
            reasons=reasons,
        )
        _print({"status": "needs_info", "response": str(response), "reasons": reasons})
        return 0
    if not brief_path.is_file():
        response = write_response(
            request_path,
            request.request_id,
            "needs_info",
            reasons=[f"brief file is missing: {request.brief_path}"],
        )
        _print(
            {
                "status": "needs_info",
                "response": str(response),
                "reasons": ["brief file is missing"],
            }
        )
        return 0
    try:
        brief = load_brief(brief_path)
    except ValueError as exc:
        reasons.append(f"brief is invalid: {exc}")
        response = write_response(
            request_path,
            request.request_id,
            "needs_info",
            reasons=reasons,
        )
        _print({"status": "needs_info", "response": str(response), "reasons": reasons})
        return 0
    out_dir = workspace_path(root / "out" / brief.name, root)
    if request.kind != "any" and getattr(brief, request.kind) is None:
        status = "needs_info"
        report = None
        verdict = None
        reasons.append(f"brief does not declare requested analysis {request.kind}")
    else:
        only = {request.kind} if request.kind != "any" else None
        report = run_simulation(brief, brief_path, root, out_dir, only)
        verdict = report["verdict"]
        status = (
            "accepted" if verdict == "pass" else "rejected" if verdict == "fail" else "needs_info"
        )
        if status == "needs_info":
            reasons.append("analysis result is unknown; missing evidence or solver output")
    response = write_response(
        request_path,
        request.request_id,
        status,
        verdict,
        report_path=(out_dir / "sim-report.json") if report is not None else None,
        reasons=reasons,
    )
    _print(
        {
            "status": status,
            "verdict": verdict,
            "report_path": str(out_dir / "sim-report.json") if report is not None else None,
            "response": str(response),
            "reasons": reasons,
        }
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = workspace_root()
    try:
        if args.command == "doctor":
            report, code = run_doctor(args.strict and not args.warn)
            _print(report)
            return code
        if args.command == "schema":
            _print(schema())
            return 0
        if args.command == "validate":
            brief_path = workspace_path(args.brief, root)
            brief = load_brief(brief_path)
            _print({"verdict": "pass", "name": brief.name, "schema_version": brief.schema_version})
            return 0
        if args.command in ("run", "gates"):
            return _run_command(args, root)
        if args.command == "report":
            out_dir = workspace_path(args.outdir, root)
            report_path = workspace_path(out_dir / "sim-report.json", root)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            _print(report)
            return {"pass": 0, "fail": 1, "unknown": 3}.get(report.get("verdict"), 3)
        if args.command == "plots":
            out_dir = workspace_path(args.outdir, root)
            report_path = workspace_path(out_dir / "sim-report.json", root)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            entries = cast(list[dict[str, str]], report.get("plots", []))
            missing: list[str] = []
            for item in entries:
                try:
                    plot_path = workspace_path(item["path"], root)
                except ValueError:
                    missing.append(item["path"])
                    continue
                if not plot_path.is_file() or sha256_file(plot_path) != item["sha256"]:
                    missing.append(item["path"])
            _print(
                {
                    "plots": entries,
                    "plot_errors": report.get("plot_errors", []),
                    "missing": missing,
                }
            )
            return 0
        if args.command == "import":
            brief_path = workspace_path(args.brief, root)
            brief = load_brief(brief_path)
            record = write_import_record(
                args.file,
                root,
                workspace_path(root / "out" / brief.name, root),
            )
            _print({"verdict": "pass", "import": record})
            return 0
        if args.command == "respond":
            return _respond(args, root)
        if args.command == "record":
            if args.record_kind == "status":
                _print(records_summary(root))
                return 0
            payload_path = workspace_path(args.json, root)
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("record payload must be a JSON object")
            _print(RECORDERS[args.record_kind](cast(dict[str, object], payload), root))
            return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _print({"verdict": "fail", "detail": str(exc)})
        return 2
    return 2
