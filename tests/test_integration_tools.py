from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sim.brief import load_brief
from sim.run import run_simulation

pytestmark = pytest.mark.tools


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_real_ngspice_divider_measure(tmp_path: Path) -> None:
    deck = tmp_path / "divider.cir"
    deck.write_text(
        "Divider\n"
        "V1 in 0 PULSE(0 5 0 1n 1n 10u 20u)\n"
        "R1 in out 1k\n"
        "C1 out 0 1n\n"
        ".tran 10n 10u\n"
        ".meas tran vout FIND v(out) AT=1u\n"
        ".end\n",
        encoding="utf-8",
    )
    brief_path = tmp_path / "divider.sim.json"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "divider",
                "spice": {
                    "deck": {
                        "netlist_path": deck.name,
                        "analyses": [".tran 10n 10u"],
                        "measures": [
                            {
                                "name": "vout",
                                "statement": ".meas tran vout FIND v(out) AT=1u",
                                "min": 3.1,
                                "max": 3.2,
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    report = run_simulation(
        load_brief(brief_path), brief_path, tmp_path, tmp_path / "out" / "divider", {"spice"}
    )

    assert report["verdict"] == "pass"
    assert report["checks"][0]["measured"] == pytest.approx(3.1606, abs=0.01)


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_real_ngspice_ac_magnitude_and_db_measures(tmp_path: Path) -> None:
    deck = tmp_path / "rc.cir"
    deck.write_text(
        "RC low-pass\nV1 in 0 AC 1\nR1 in out 1k\nC1 out 0 1u\n.end\n",
        encoding="utf-8",
    )
    brief_path = tmp_path / "rc.sim.json"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "rc_ac",
                "spice": {
                    "deck": {
                        "netlist_path": deck.name,
                        "analyses": [".ac dec 20 10 10k"],
                        "measures": [
                            {
                                "name": "vout",
                                "statement": ".meas ac vout FIND vm(out) AT=159.1549431",
                                "min": 0.65,
                                "max": 0.76,
                            },
                            {
                                "name": "vout_db",
                                "statement": ".meas ac vout_db FIND vdb(out) AT=159.1549431",
                                "min": -3.1,
                                "max": -2.9,
                            },
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    report = run_simulation(
        load_brief(brief_path), brief_path, tmp_path, tmp_path / "out" / "rc_ac", {"spice"}
    )
    checks = {item["id"]: item for item in report["checks"]}

    assert report["verdict"] == "pass"
    assert checks["spice.vout"]["measured"] == pytest.approx(0.7071, abs=0.002)
    assert checks["spice.vout_db"]["measured"] == pytest.approx(-3.0103, abs=0.03)


@pytest.mark.skipif(shutil.which("ccx") is None, reason="CalculiX is not installed")
@pytest.mark.parametrize("element", ["C3D8I", "C3D20R"])
def test_real_calculix_adapter_emits_report(tmp_path: Path, element: str) -> None:
    brief_path = tmp_path / "cantilever.sim.json"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "cantilever",
                "fem": {
                    "geometry": {
                        "kind": "cantilever_box",
                        "length_mm": 100,
                        "width_mm": 25,
                        "height_mm": 10,
                    },
                    "material": {
                        "name": "Al-6061-T6",
                        "youngs_mpa": 69000,
                        "poisson": 0.33,
                        "yield_mpa": 276,
                    },
                    "load": {"kind": "tip_force", "force_n": 10, "direction": "-z"},
                    "mesh": {"nx": 2, "ny": 1, "nz": 1, "element": element},
                    "limits": {"min_safety_factor": 2, "max_deflection_mm": 1},
                    "cross_check_tolerance": 0.15,
                },
            }
        ),
        encoding="utf-8",
    )

    fem_dir = tmp_path / "out" / "cantilever" / "fem"
    report = run_simulation(
        load_brief(brief_path), brief_path, tmp_path, tmp_path / "out" / "cantilever", {"fem"}
    )
    checks = {item["id"]: item for item in report["checks"]}
    dat_text = (fem_dir / "simulation.dat").read_text(encoding="utf-8")

    assert report["verdict"] == "pass"
    assert (fem_dir / "simulation.inp").is_file()
    assert checks["fem.deflection"]["verdict"] == "pass"
    assert checks["fem.cross_check"]["verdict"] == "pass"
    cross_check_measurement = checks["fem.cross_check"]["measured"]
    assert cross_check_measurement is not None
    assert cross_check_measurement <= 0.15
    assert "for set NALL" in dat_text
