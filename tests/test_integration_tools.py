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
        "Divider\nV1 in 0 DC 5\nR1 in out 1k\nR2 out 0 1k\n.op\n.meas op vout FIND v(out)\n.end\n",
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
                        "analyses": [".op"],
                        "measures": [
                            {
                                "name": "vout",
                                "statement": ".meas op vout FIND v(out)",
                                "min": 2.4,
                                "max": 2.6,
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
    assert report["checks"][0]["measured"] == pytest.approx(2.5, abs=0.01)


@pytest.mark.skipif(shutil.which("ccx") is None, reason="CalculiX is not installed")
def test_real_calculix_adapter_emits_report(tmp_path: Path) -> None:
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
                    "mesh": {"nx": 2, "ny": 1, "nz": 1, "element": "C3D8I"},
                    "limits": {"max_deflection_mm": 5},
                },
            }
        ),
        encoding="utf-8",
    )

    report = run_simulation(
        load_brief(brief_path), brief_path, tmp_path, tmp_path / "out" / "cantilever", {"fem"}
    )

    assert (tmp_path / "out" / "cantilever" / "fem" / "simulation.inp").is_file()
    assert report["checks"]
