from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from sim.adapters.calculix import generate_input, parse_dat, run_calculix
from sim.adapters.ngspice import parse_measures, render_deck, run_ngspice
from sim.brief import FemSection, Measure, SimulationBrief, SpiceDeck, SpiceElement
from sim.run import run_simulation


def _fem() -> FemSection:
    return FemSection.model_validate(
        {
            "geometry": {
                "kind": "cantilever_box",
                "length_mm": 100,
                "width_mm": 10,
                "height_mm": 10,
            },
            "material": {
                "name": "aluminum",
                "youngs_mpa": 70000,
                "poisson": 0.33,
                "yield_mpa": 240,
            },
            "load": {"kind": "tip_force", "force_n": 10, "direction": "-z"},
            "mesh": {"nx": 1, "ny": 1, "nz": 1, "element": "C3D20R"},
        }
    )


def test_calculix_c3d20r_mesh_and_output_parsing() -> None:
    deck = generate_input(_fem())
    assert "*ELEMENT, TYPE=C3D20R, ELSET=EALL" in deck
    assert "*BOUNDARY\nFIXED, 1, 3, 0" in deck
    assert "U\n*EL PRINT" in deck
    assert deck.count(", 3, -1.25") == 8

    displacement, stress = parse_dat(
        "displacements (vx, vy, vz)\n"
        "1 0.0 0.0 -0.25\n"
        "2 0.0 0.0 0.5\n"
        "stresses (elem, integ. point, sxx, syy, szz, sxy, syz, szx)\n"
        "1 1 100 0 0 0 0 0\n"
    )
    assert displacement == 0.5
    assert stress == 100


def test_ngspice_missing_binary_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_NGSPICE", str(tmp_path / "missing-ngspice"))
    deck = SpiceDeck(
        elements=[SpiceElement(ref="1", kind="R", nodes=["in", "0"], value="1k")],
        analyses=[".op"],
        measures=[Measure(name="vout", statement=".meas op vout FIND v(in)", min=1)],
    )

    checks, artifacts = run_ngspice(deck, tmp_path, tmp_path / "out")
    assert checks[0].verdict == "unknown"
    assert artifacts == {}


def test_ngspice_failed_or_missing_measure_is_unknown() -> None:
    deck = SpiceDeck(
        elements=[SpiceElement(ref="1", kind="R", nodes=["in", "0"], value="1k")],
        analyses=[".op"],
        measures=[
            Measure(name="vout", statement=".meas op vout FIND v(in)", min=1),
            Measure(name="vin", statement=".meas op vin FIND v(in)", min=1),
        ],
    )

    checks = parse_measures("vout = failed\n", deck)

    assert [item.verdict for item in checks] == ["unknown", "unknown"]


def test_spice_relative_include_resolves_inside_workspace(tmp_path: Path) -> None:
    include = tmp_path / "models.lib"
    include.write_text(".model DTEST D\n", encoding="utf-8")
    netlist = tmp_path / "deck.cir"
    netlist.write_text(
        'Test\n.include "models.lib"\n.op\n.meas op vout FIND v(in)\n.end\n',
        encoding="utf-8",
    )
    deck = SpiceDeck(
        netlist_path=netlist.name,
        analyses=[".op"],
        measures=[Measure(name="vout", statement=".meas op vout FIND v(in)")],
    )

    rendered = render_deck(deck, tmp_path)

    assert f'.include "{include}"' in rendered


def test_structured_spice_deck_resolves_declared_model_include(tmp_path: Path) -> None:
    include = tmp_path / "models.lib"
    include.write_text(".model DTEST D\n", encoding="utf-8")
    deck = SpiceDeck(
        elements=[SpiceElement(ref="1", kind="R", nodes=["in", "0"], value="1k")],
        models=['.include "models.lib"'],
        analyses=[".op"],
    )

    rendered = render_deck(deck, tmp_path)

    assert f'.include "{include}"' in rendered


def test_spice_netlist_uses_declared_analyses_and_measurements(tmp_path: Path) -> None:
    netlist = tmp_path / "deck.cir"
    netlist.write_text(
        "Test\nR1 in out 1k\n.ac dec 10 1 1k\n.meas ac old FIND v(out)\n.end\n",
        encoding="utf-8",
    )
    deck = SpiceDeck(
        netlist_path=netlist.name,
        analyses=[".op"],
        measures=[
            Measure(
                name="vout",
                statement=".meas op vout FIND v(out)",
                min=1,
            )
        ],
    )

    rendered = render_deck(deck, tmp_path)

    assert rendered.count(".op") == 1
    assert ".ac dec 10 1 1k" not in rendered
    assert "old FIND" not in rendered
    assert rendered.count(".meas op vout FIND v(out)") == 1
    assert rendered.index(".op") < rendered.index(".end")


def test_spice_rejects_multiple_end_statements(tmp_path: Path) -> None:
    netlist = tmp_path / "deck.cir"
    netlist.write_text("Test\n.end\n.end\n", encoding="utf-8")
    deck = SpiceDeck(netlist_path=netlist.name, analyses=[".op"])

    with pytest.raises(ValueError, match=r"at most one \.end"):
        render_deck(deck, tmp_path)


def test_spice_include_cannot_escape_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-model.lib"
    outside.write_text(".model DTEST D\n", encoding="utf-8")
    netlist = tmp_path / "deck.cir"
    netlist.write_text(
        f".include ../{outside.name}\n.op\n.meas op vout FIND v(in)\n.end\n",
        encoding="utf-8",
    )
    deck = SpiceDeck(
        netlist_path=netlist.name,
        analyses=[".op"],
        measures=[Measure(name="vout", statement=".meas op vout FIND v(in)")],
    )

    try:
        render_deck(deck, tmp_path)
    except ValueError as exc:
        assert "outside the workspace" in str(exc)
    else:
        raise AssertionError("outside SPICE include was accepted")


def test_spice_rejects_control_blocks_in_netlists_and_includes(tmp_path: Path) -> None:
    included = tmp_path / "models.lib"
    included.write_text(".control\nshell touch marker\n.endc\n", encoding="utf-8")
    netlist = tmp_path / "deck.cir"
    netlist.write_text('.include "models.lib"\n.end\n', encoding="utf-8")
    deck = SpiceDeck(netlist_path=netlist.name, analyses=[".op"])

    with pytest.raises(ValueError, match="control blocks are not supported"):
        render_deck(deck, tmp_path)

    netlist.write_text(".control\nshell touch marker\n.endc\n.end\n", encoding="utf-8")

    with pytest.raises(ValueError, match="control blocks are not supported"):
        render_deck(deck, tmp_path)


def test_rfsim_rejects_ambiguous_result_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "output = Path(sys.argv[2])\n"
        '(output / "results.s1p").write_text("# Hz S RI R 50\\n1 0 0\\n")\n'
        '(output / "results.s2p").write_text("# Hz S RI R 50\\n1 0 0 0 0\\n")\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SIM_OPENEMS_PYTHON", sys.executable)
    brief = SimulationBrief.model_validate(
        {
            "schema_version": 1,
            "name": "rf",
            "rf": {
                "rfsim": {
                    "model_path": "model.json",
                    "runner_path": runner.name,
                }
            },
        }
    )

    brief_path = tmp_path / "rf.sim.json"
    brief_path.write_text(
        brief.model_dump_json(),
        encoding="utf-8",
    )
    report = run_simulation(brief, brief_path, tmp_path, tmp_path / "out", only={"rf"})

    assert report["verdict"] == "unknown"
    assert "exactly one results.sNp" in report["checks"][0]["detail"]


def test_ngspice_nonzero_exit_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "ngspice-failure"
    binary.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | 0o111)
    monkeypatch.setenv("SIM_NGSPICE", str(binary))
    deck = SpiceDeck(
        elements=[SpiceElement(ref="1", kind="R", nodes=["in", "0"], value="1k")],
        analyses=[".op"],
        measures=[Measure(name="vout", statement=".meas op vout FIND v(in)", min=1)],
    )

    checks, artifacts = run_ngspice(deck, tmp_path, tmp_path / "out")
    assert checks[0].verdict == "unknown"
    assert artifacts["returncode"] == 17


def test_ngspice_timeout_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "ngspice-timeout"
    binary.write_text("#!/bin/sh\nsleep 2\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | 0o111)
    monkeypatch.setenv("SIM_NGSPICE", str(binary))
    deck = SpiceDeck(
        elements=[SpiceElement(ref="1", kind="R", nodes=["in", "0"], value="1k")],
        analyses=[".op"],
        measures=[Measure(name="vout", statement=".meas op vout FIND v(in)", min=1)],
        timeout_s=0.05,
    )

    checks, _ = run_ngspice(deck, tmp_path, tmp_path / "out")
    assert checks[0].verdict == "unknown"


def test_calculix_adapter_runs_solver_as_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "ccx-stub"
    binary.write_text(
        "#!/bin/sh\n"
        "cat > simulation.dat <<'EOF'\n"
        "displacements (vx, vy, vz)\n"
        "1 0.0 0.0 -0.25\n"
        "2 0.0 0.0 0.5\n"
        "stresses (elem, integ. point, sxx, syy, szz, sxy, syz, szx)\n"
        "1 1 100 0 0 0 0 0\n"
        "EOF\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | 0o111)
    monkeypatch.setenv("SIM_CCX", str(binary))

    checks, artifacts = run_calculix(_fem(), tmp_path / "fem")

    assert artifacts["returncode"] == 0
    assert (tmp_path / "fem" / "simulation.inp").is_file()
    assert {item.id: item.verdict for item in checks}["fem.safety_factor"] == "pass"


def test_calculix_missing_solver_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIM_CCX", str(tmp_path / "missing-ccx"))

    checks, _ = run_calculix(_fem(), tmp_path / "fem")

    assert checks[0].verdict == "unknown"


def test_spice_wca_updates_declared_params_and_uses_unbounded_measure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sim.brief import load_brief
    from sim.run import run_simulation

    deck_path = tmp_path / "corner.cir"
    deck_path.write_text(
        "Corner model\n"
        ".param Rtop=1k Rbottom=1k\n"
        "R1 in out {Rtop}\n"
        "R2 out 0 {Rbottom}\n"
        ".op\n"
        ".meas op vout FIND v(out)\n"
        ".end\n",
        encoding="utf-8",
    )
    brief_path = tmp_path / "corner.sim.json"
    brief_path.write_text(
        """
        {
          "schema_version": 1,
          "name": "corner",
          "spice": {
            "deck": {
              "netlist_path": "corner.cir",
              "analyses": [".op"],
              "measures": [
                {"name": "vout", "statement": ".meas op vout FIND v(out)"}
              ]
            }
          },
          "wca": {
            "parameters": [
              {"name": "Rtop", "nominal": 1000, "tol_pct": 10},
              {"name": "Rbottom", "nominal": 1000, "tol_pct": 10}
            ],
            "outputs": [
              {"name": "corner_vout", "spice_measure": "vout", "min": 0.4, "max": 0.6}
            ],
            "methods": ["EVA"]
          }
        }
        """,
        encoding="utf-8",
    )
    rendered: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cwd = kwargs.get("cwd")
        if isinstance(cwd, (str, Path)):
            corner_deck = (Path(cwd) / "deck.cir").read_text(encoding="utf-8")
            rendered.append(corner_deck)
        return subprocess.CompletedProcess(command, 0, stdout="vout = 0.5\n", stderr="")

    monkeypatch.setattr("sim.run.subprocess.run", fake_run)
    brief = load_brief(brief_path)

    report = run_simulation(
        brief,
        brief_path,
        tmp_path,
        tmp_path / "out" / "corner",
        {"spice", "wca"},
    )

    assert report["verdict"] == "unknown"
    assert len(rendered) == 5
    assert all(".param Rtop=1k Rbottom=1k" not in deck for deck in rendered[1:])
    assert all(
        len(line.split()) == 3
        for deck in rendered[1:]
        for line in deck.splitlines()
        if line.startswith(".param ")
    )
    assert (
        next(item for item in report["checks"] if item["id"] == "wca.EVA.corner_vout")["verdict"]
        == "pass"
    )
