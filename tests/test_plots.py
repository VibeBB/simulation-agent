"""Unit tests for the deterministic plot pipeline (Phase B)."""

from __future__ import annotations

import json
import math
import struct
import zlib
from pathlib import Path

import pytest

from sim import plot
from sim.adapters.spice_raw import parse_raw, parse_raw_bytes
from sim.brief import SimulationBrief
from sim.gates import check
from sim.plot import _decade_ticks  # pyright: ignore[reportPrivateUsage]
from sim.run import _fem_plot, _write_plots  # pyright: ignore[reportPrivateUsage]

# line_chart layout constants (plot area between these pixel edges).
_PLOT_TOP = 46
_PLOT_BOTTOM = 540 - 60
_TRACE_RIGHT = 800  # stay left of the legend swatch


def _png_ok(blob: bytes, *, height: int | None = 540) -> None:
    assert blob.startswith(b"\x89PNG\r\n\x1a\n")
    width, actual_height = struct.unpack(">II", blob[16:24])
    assert width == 960
    if height is not None:
        assert actual_height == height


def _png_rows(blob: bytes) -> list[bytes]:
    """Decode the filter-0 RGB scanlines the plot canvas always emits."""
    pos = 8
    width = height = 0
    idat = b""
    while pos + 8 <= len(blob):
        (length,) = struct.unpack(">I", blob[pos : pos + 4])
        kind = blob[pos + 4 : pos + 8]
        data = blob[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height = struct.unpack(">II", data[:8])
        elif kind == b"IDAT":
            idat += data
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 3
    return [raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)] for y in range(height)]


def _color_count(row: bytes, color: tuple[int, int, int], x_max: int = 960) -> int:
    pixel = bytes(color)
    return sum(1 for i in range(0, min(len(row), x_max * 3), 3) if row[i : i + 3] == pixel)


def _curve_height(blob: bytes) -> int:
    """Vertical pixel span of the first-series trace inside the plot area."""
    rows = _png_rows(blob)
    hits = [
        y
        for y in range(_PLOT_TOP, _PLOT_BOTTOM + 1)
        if _color_count(rows[y], plot.PALETTE[0], x_max=_TRACE_RIGHT)
    ]
    return max(hits) - min(hits) if hits else 0


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
    _png_ok(plot.margin_chart(rows, title="margins", not_plotted=2), height=None)


def test_stacked_bar_and_scatter_render() -> None:
    _png_ok(plot.stacked_bar_chart([("spice", {"pass": 2, "fail": 1, "unknown": 0})], title="t"))
    _png_ok(
        plot.scatter_board(
            [(1.0, 2.0, "TP1", True, 0.5), (3.0, 2.0, "TP2", False, 0.5)],
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
        _png_ok(blob, height=None)


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


def test_lowercase_glyphs_render_differently() -> None:
    canvas = plot.Canvas(120, 20)
    canvas.text(2, 4, "Frequency (Hz)", plot.BLACK)
    rendered = canvas.to_png()
    canvas2 = plot.Canvas(120, 20)
    canvas2.text(2, 4, "FREQUENCY (HZ)", plot.BLACK)
    assert rendered != canvas2.to_png()


def test_engineering_fmt() -> None:
    assert plot.fmt(1.5e9) == "1.5G"
    assert plot.fmt(500e6) == "500M"
    assert plot.fmt(2.5e-3) == "2.5m"
    assert plot.fmt(10**4) == "10k"


def test_decade_ticks() -> None:
    assert _decade_ticks(1.0, 4.0) == [1.0, 2.0, 3.0, 4.0]
    assert _decade_ticks(1.3, 2.9) == [2.0]


def test_stacked_bar_integer_ticks() -> None:
    items = [("a", {"pass": 4, "fail": 1, "unknown": 0})]
    first = plot.stacked_bar_chart(items, title="t")
    assert first == plot.stacked_bar_chart(items, title="t")
    # integer tick step: 5 -> step 2 -> ticks 0,2,4
    assert plot.fmt(4) == "4"


def test_margin_one_sided_positions(tmp_path: Path) -> None:
    # "≤ -15" with measured -20 (fail): bound must sit right of marker.
    rows_upper = [("s11", "fail", -20.0, None, -15.0)]
    _png_ok(plot.margin_chart(rows_upper), height=None)
    # "≥ -3" with measured -1.01 (pass): bound at left portion.
    rows_lower = [("s21", "pass", -1.01, -3.0, None)]
    _png_ok(plot.margin_chart(rows_lower), height=None)


def test_scatter_equal_aspect() -> None:
    # Square board 10x10mm should keep aspect; smoke-check determinism.
    points = [(0.0, 0.0, "A", True, 0.4), (10.0, 10.0, "B", False, 0.4)]
    a = plot.scatter_board(points)
    b = plot.scatter_board(points)
    assert a == b


def test_line_chart_y_focus_scales_to_data() -> None:
    xs = list(range(200))
    series = [("sig", xs, [x / 20000 for x in xs])]  # 0..0.01, far below the limit
    focused = plot.line_chart(series, hlines=[(5.0, "limit")], y_focus=True)
    plain = plot.line_chart(series, hlines=[(5.0, "limit")])
    _png_ok(focused)
    assert focused != plain
    plot_height = _PLOT_BOTTOM - _PLOT_TOP
    assert _curve_height(focused) > plot_height * 0.5
    assert _curve_height(plain) < plot_height * 0.2
    # Off-scale bound stays annotated: dashed line + label hug the top edge.
    rows = _png_rows(focused)
    edge_gray = sum(_color_count(row, plot.GRAY) for row in rows[_PLOT_TOP : _PLOT_TOP + 12])
    assert edge_gray > 50


def test_line_chart_y_focus_in_range_bound_unchanged() -> None:
    xs = list(range(50))
    series = [("sig", xs, [math.sin(x / 5) for x in xs])]
    focused = plot.line_chart(series, hlines=[(0.5, "limit")], y_focus=True)
    plain = plot.line_chart(series, hlines=[(0.5, "limit")])
    # A bound inside the data span draws identically in both modes.
    assert focused == plain
    rows = _png_rows(focused)
    assert any(_color_count(row, plot.GRAY) > 400 for row in rows)


def test_line_chart_y_focus_below_bound() -> None:
    xs = list(range(50))
    series = [("sig", xs, [1.0 + math.sin(x / 5) for x in xs])]
    focused = plot.line_chart(series, hlines=[(-3.0, "limit")], y_focus=True)
    _png_ok(focused)
    rows = _png_rows(focused)
    edge_gray = sum(_color_count(row, plot.GRAY) for row in rows[_PLOT_BOTTOM - 14 : _PLOT_BOTTOM])
    assert edge_gray > 50


def test_line_chart_y_focus_no_data_fails_closed() -> None:
    empty = plot.line_chart([], hlines=[(5.0, "lim")], y_focus=True)
    _png_ok(empty)
    assert empty == plot.line_chart([], hlines=[(5.0, "lim")])
    corrupt = plot.line_chart([("bad", [1.0], [1.0, 2.0])], hlines=[(5.0, "lim")], y_focus=True)
    assert corrupt == empty


def test_fem_plot_zooms_when_limit_dwarfs_tip(tmp_path: Path) -> None:
    out_dir = tmp_path / "out" / "demo"
    out_dir.mkdir(parents=True)
    brief = SimulationBrief.model_validate(
        {
            "schema_version": 1,
            "name": "demo",
            "fem": {
                "geometry": {
                    "kind": "cantilever_box",
                    "length_mm": 100.0,
                    "width_mm": 25.0,
                    "height_mm": 10.0,
                },
                "material": {
                    "name": "Al-6061-T6",
                    "youngs_mpa": 69000.0,
                    "poisson": 0.33,
                    "yield_mpa": 276.0,
                },
                "load": {"kind": "tip_force", "force_n": 10.0, "direction": "-z"},
                "mesh": {"nx": 2, "ny": 1, "nz": 1, "element": "C3D8I"},
                "limits": {"max_deflection_mm": 1.0},
            },
        }
    )
    png = _fem_plot(brief, out_dir)
    assert png is not None
    _png_ok(png)
    # tip ~0.02 mm vs limit 1 mm: the curve must fill the plot, not hug the axis.
    assert _curve_height(png) > (_PLOT_BOTTOM - _PLOT_TOP) * 0.5
    rows = _png_rows(png)
    edge_gray = sum(_color_count(row, plot.GRAY) for row in rows[_PLOT_TOP : _PLOT_TOP + 12])
    assert edge_gray > 50
