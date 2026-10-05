"""Unit tests for the deterministic plot pipeline (Phase B)."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from sim import plot
from sim.adapters.spice_raw import parse_raw, parse_raw_bytes
from sim.brief import SimulationBrief
from sim.gates import check
from sim.run import _write_plots  # pyright: ignore[reportPrivateUsage]


def _png_ok(blob: bytes) -> None:
    assert blob.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", blob[16:24])
    assert width == 960 and height == 540


def test_png_is_deterministic() -> None:
    series = [("v(out)", [1, 2, 3, 4], [0.1, 0.5, 0.4, 0.9])]
    first = plot.line_chart(series, title="t", xlabel="x", ylabel="y")
    second = plot.line_chart(series, title="t", xlabel="x", ylabel="y")
    assert first == second
    _png_ok(first)


def test_parse_limit_forms() -> None:
    assert plot.parse_limit("≤ 1.2 V") == (None, 1.2)
    assert plot.parse_limit("≥ 0.5") == (0.5, None)
    assert plot.parse_limit("min 0.4; max 0.6") == (0.4, 0.6)
    assert plot.parse_limit("min None; max 3.3") == (None, 3.3)
    assert plot.parse_limit("0.9 to 1.1") == (0.9, 1.1)
    assert plot.parse_limit("≤ 5 % or terminated") == (None, 5.0)
    assert plot.parse_limit("no numbers here") is None


def test_margin_chart_renders_rows() -> None:
    rows = [
        ("a.upper", "pass", 0.5, None, 1.0),
        ("a.lower", "fail", 0.2, 0.4, None),
        ("a.band", "unknown", 0.6, 0.4, 0.8),
    ]
    _png_ok(plot.margin_chart(rows, title="margins", not_plotted=2))


def test_stacked_bar_and_scatter_render() -> None:
    _png_ok(plot.stacked_bar_chart([("spice", {"pass": 2, "fail": 1, "unknown": 0})], title="t"))
    _png_ok(
        plot.scatter_board(
            [(1.0, 2.0, "TP1", True), (3.0, 2.0, "TP2", False)],
            links=[(1.0, 2.0, 3.0, 2.0)],
            circles=[(1.0, 2.0, 0.5)],
        )
    )


def _synthetic_raw() -> bytes:
    variables = ["frequency", "v(out)"]
    points = 3
    header = (
        "Title: synthetic\n"
        "Date: now\n"
        "Plotname: AC Analysis\n"
        "Flags: complex\n"
        f"No. Variables: {len(variables)}\n"
        f"No. Points: {points}\n"
        "Variables:\n"
        + "".join(f"\t{i}\t{name}\tin\n" for i, name in enumerate(variables))
        + "Binary:\n"
    )
    blob = header.encode("ascii")
    for index in range(points):
        for _ in variables:
            blob += struct.pack("<dd", 10.0 * (index + 1), 0.0)
    return blob


def test_parse_raw_bytes_complex() -> None:
    blocks = parse_raw_bytes(_synthetic_raw())
    assert len(blocks) == 1
    block = blocks[0]
    assert block.plotname == "AC Analysis"
    assert block.complex_values is True
    assert block.variables == ("frequency", "v(out)")
    assert block.points == 3
    assert block.data[0][0] == complex(10.0, 0.0)


def test_parse_raw_rejects_garbage(tmp_path: Path) -> None:
    bad = tmp_path / "raw.bin"
    bad.write_bytes(b"not a raw file")
    with pytest.raises(ValueError):
        parse_raw(bad)


def test_write_plots_reports_errors_never_raises(tmp_path: Path) -> None:
    out_dir = tmp_path / "out" / "demo"
    out_dir.mkdir(parents=True)
    checks = [
        check("spice.v", "spice", "pass", "ok", measured=0.7, limit="≤ 1.0 V"),
        check("fem.defl", "fem", "fail", "bad"),
    ]
    brief = SimulationBrief.model_validate(
        {
            "schema_version": 1,
            "name": "demo",
            "spice": {"deck": {"netlist_path": "x.cir", "analyses": [".ac dec 5 10 1k"]}},
        }
    )
    plots, errors = _write_plots(brief, checks, out_dir, tmp_path, None)
    names = {entry["path"] for entry in plots}
    assert "out/demo/plots/summary.png" in names
    assert "out/demo/plots/margin-spice.png" in names
    assert any(error.startswith("spice:") for error in errors)
    for entry in plots:
        blob = (tmp_path / entry["path"]).read_bytes()
        import hashlib

        assert hashlib.sha256(blob).hexdigest() == entry["sha256"]
        _png_ok(blob)


def test_dft_and_fem_plots_from_brief(tmp_path: Path) -> None:
    out_dir = tmp_path / "out" / "demo"
    out_dir.mkdir(parents=True)
    brief = SimulationBrief.model_validate(
        {
            "schema_version": 1,
            "name": "demo",
            "dft": {
                "required": "listed",
                "test_points": [
                    {
                        "ref": "TP1",
                        "net": "VCC",
                        "pad_diameter_mm": 1.0,
                        "x_mm": 1.0,
                        "y_mm": 1.0,
                        "side": "top",
                    },
                    {
                        "ref": "TP2",
                        "net": "VCC",
                        "pad_diameter_mm": 1.0,
                        "x_mm": 1.5,
                        "y_mm": 1.0,
                        "side": "bottom",
                    },
                ],
                "min_pitch_mm": 2.0,
            },
            "fem": {
                "geometry": {
                    "kind": "cantilever_box",
                    "length_mm": 50.0,
                    "width_mm": 10.0,
                    "height_mm": 2.0,
                },
                "material": {
                    "name": "pla",
                    "youngs_mpa": 3500.0,
                    "poisson": 0.36,
                    "yield_mpa": 50.0,
                },
                "load": {"kind": "tip_force", "force_n": 5.0, "direction": "-z"},
                "mesh": {"nx": 4, "ny": 2, "nz": 1, "element": "C3D20R"},
                "limits": {"max_deflection_mm": 5.0},
            },
        }
    )
    plots, _errors = _write_plots(brief, [], out_dir, tmp_path, None)
    names = {entry["path"] for entry in plots}
    assert "out/demo/plots/dft-testpoints.png" in names
    assert "out/demo/plots/fem-deflection.png" in names
    checklists = {entry["checklist"] for entry in plots}
    assert "dft-testpoints" in checklists
    assert "fem-deflection" in checklists


@pytest.mark.tools
def test_spice_plot_from_real_ngspice(tmp_path: Path) -> None:
    import shutil
    import subprocess

    if shutil.which("ngspice") is None:
        pytest.skip("ngspice not installed")
    cir = tmp_path / "rc.cir"
    cir.write_text("RC filter\nVin in 0 ac 1\nR1 in out 1k\nC1 out 0 1u\n.ac dec 5 10 1k\n.end\n")
    raw = tmp_path / "raw.bin"
    subprocess.run(
        ["ngspice", "-b", "-r", str(raw), "-o", str(tmp_path / "log"), str(cir)],
        check=True,
        capture_output=True,
    )
    blocks = parse_raw(raw)
    assert blocks
    assert any(name.lower().startswith("v(") for name in blocks[0].variables)


def test_report_lists_plots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sim.mcp_server import dispatch_tool

    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    brief_path = tmp_path / "b.sim.json"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "b",
                "thermal": {
                    "ambient_c": 25.0,
                    "components": [{"ref": "r1", "power_w": 0.5, "tj_max_c": 125.0}],
                },
            }
        )
    )
    payload = dispatch_tool("sim_run", {"brief": "b.sim.json"})
    report = json.loads((tmp_path / "out" / "b" / "sim-report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == 2
    assert any(item["checklist"] == "sim-summary" for item in report["plots"])
    listed = payload["plots"]
    assert listed
    markdown = (tmp_path / "out" / "b" / "sim-report.md").read_text(encoding="utf-8")
    assert "## Plots" in markdown
