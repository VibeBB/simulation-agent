"""Simulation orchestration and RF predicates."""

from __future__ import annotations

import itertools
import json
import math
import os
import random
import re
import subprocess
from pathlib import Path
from typing import cast

from . import __version__
from .adapters.calculix import run_calculix
from .adapters.ngspice import parse_measures, render_deck, run_ngspice
from .analysis import (
    microstrip_impedance,
    run_dft,
    run_emc,
    run_pdn_rail,
    run_thermal,
    run_wca,
)
from .brief import (
    EmcSignal,
    PdnBranch,
    PdnLoad,
    SimulationBrief,
    WcaParameter,
    WcaSection,
)
from .gates import GateCheck, check
from .imports import import_source
from .report import SimulationReport, write_outputs
from .tools import discover_tools
from .touchstone import TouchstoneData
from .touchstone import parse as parse_touchstone
from .workspace import reject_symlinks, workspace_path


def _wca_delta(parameter: WcaParameter) -> float:
    tolerance = (
        parameter.tol_abs
        if parameter.tol_abs is not None
        else abs(parameter.nominal) * (parameter.tol_pct or 0) / 100
    )
    temperature = (
        abs(parameter.nominal * parameter.temp_coeff_ppm / 1e6) * parameter.temp_range_c
        if parameter.temp_coeff_ppm is not None and parameter.temp_range_c is not None
        else 0
    )
    return tolerance + temperature


def _object_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[object, object], value)
    result: dict[str, object] = {}
    for key, item in mapping.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _import_records(
    imports: list[dict[str, object]], system: str, collection: str
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for entry in imports:
        if entry.get("system") != system:
            continue
        extracted = _object_mapping(entry.get("extracted"))
        if extracted is None:
            continue
        items = extracted.get(collection)
        if not isinstance(items, list):
            continue
        for item in cast(list[object], items):
            record = _object_mapping(item)
            if record is not None:
                records.append(record)
    return records


def _keyed_import_records(
    imports: list[dict[str, object]], system: str, collection: str, key: str
) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for record in _import_records(imports, system, collection):
        value = record.get(key)
        if isinstance(value, str):
            records[value] = record
    return records


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _rf_checks(data: TouchstoneData, brief: SimulationBrief) -> list[GateCheck]:
    results: list[GateCheck] = []
    rf = brief.rf
    if rf is None:
        return results
    for band in rf.bands:
        gate_id = f"rf.band.{band.name}"
        if data.non_passive:
            results.append(check(gate_id, "rf", "unknown", "non-passive result"))
            continue
        samples = [
            sample
            for sample in data.samples
            if band.f_min_hz <= sample.frequency_hz <= band.f_max_hz
        ]
        if not samples:
            results.append(check(gate_id, "rf", "unknown", "no Touchstone data in frequency band"))
            continue
        sample_checks: list[tuple[bool | None, str, float | None]] = []
        if band.s11_max_db is not None:
            s11_values = [
                20 * math.log10(max(abs(sample.matrix[0][0]), 1e-300)) for sample in samples
            ]
            max_s11 = max(s11_values)
            sample_checks.append((max_s11 <= band.s11_max_db, "S11 maximum", max_s11))
        if band.s21_min_db is not None:
            if data.ports < 2:
                sample_checks.append((None, "S21 minimum requires a 2-port result", None))
            else:
                values = [
                    20 * math.log10(max(abs(sample.matrix[1][0]), 1e-300)) for sample in samples
                ]
                min_s21 = min(values)
                sample_checks.append((min_s21 >= band.s21_min_db, "S21 minimum", min_s21))
        if band.vswr_max is not None:
            magnitudes = [abs(sample.matrix[0][0]) for sample in samples]
            maximum = max(magnitudes)
            vswr = math.inf if maximum >= 1 else (1 + maximum) / (1 - maximum)
            sample_checks.append(
                (None if not math.isfinite(vswr) else vswr <= band.vswr_max, "VSWR maximum", vswr)
            )
        if not sample_checks:
            results.append(check(gate_id, "rf", "unknown", "RF band has no acceptance limits"))
            continue
        for passed, label, value in sample_checks:
            results.append(
                check(
                    f"{gate_id}.{label.lower().replace(' ', '_')}",
                    "rf",
                    "unknown" if passed is None else ("pass" if passed else "fail"),
                    label if value is None else f"{label}: {value:.9g}",
                    measured=value if value is not None and math.isfinite(value) else None,
                    limit=(
                        f"≤ {band.s11_max_db:.9g} dB"
                        if label == "S11 maximum" and band.s11_max_db is not None
                        else (
                            f"≥ {band.s21_min_db:.9g} dB"
                            if label == "S21 minimum" and band.s21_min_db is not None
                            else (
                                f"≤ {band.vswr_max:.9g}"
                                if label == "VSWR maximum" and band.vswr_max is not None
                                else None
                            )
                        )
                    ),
                )
            )
    return results


def _run_rfsim(
    brief: SimulationBrief, workspace: Path, out_dir: Path
) -> tuple[TouchstoneData | None, str]:
    assert brief.rf is not None and brief.rf.rfsim is not None
    model = workspace_path(brief.rf.rfsim.model_path, workspace)
    runner = (
        str(workspace_path(brief.rf.rfsim.runner_path, workspace))
        if brief.rf.rfsim.runner_path is not None
        else os.environ.get("SIM_RFSIM_RUNNER", "/opt/kicad-rfsim/plugins/runner.py")
    )
    if not Path(runner).is_file():
        return None, f"KiCad-rfsim runner does not exist: {runner}"
    output = out_dir / "rf"
    try:
        reject_symlinks(output)
        output.mkdir(parents=True, exist_ok=True)
        reject_symlinks(output)
    except (OSError, ValueError) as exc:
        return None, f"unsafe KiCad-rfsim output directory: {exc}"
    try:
        subprocess.run(
            [os.environ.get("SIM_OPENEMS_PYTHON", "python3"), runner, str(model), str(output)],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=brief.rf.rfsim.timeout_s,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"KiCad-rfsim failed: {exc}"
    try:
        reject_symlinks(output)
    except (OSError, ValueError) as exc:
        return None, f"unsafe KiCad-rfsim generated output: {exc}"
    results = sorted(output.glob("results.s*p"))
    if len(results) != 1:
        return None, "KiCad-rfsim did not produce exactly one results.sNp file"
    try:
        return parse_touchstone(results[0]), str(results[0])
    except (OSError, ValueError) as exc:
        return None, f"Touchstone parse failed: {exc}"


def run_simulation(
    brief: SimulationBrief,
    brief_path: Path,
    workspace: Path,
    out_dir: Path,
    only: set[str] | None = None,
) -> SimulationReport:
    known = {"spice", "pdn", "thermal", "wca", "emc", "dft", "fem", "rf"}
    if only is not None and not only <= known:
        raise ValueError(f"unknown analysis in --only: {', '.join(sorted(only - known))}")
    selected = only or known
    brief_path = workspace_path(brief_path, workspace)
    out_dir = workspace_path(out_dir, workspace)
    out_dir.mkdir(parents=True, exist_ok=True)
    reject_symlinks(out_dir)
    tools = discover_tools()
    tools["simulation-agent"] = {"available": True, "version": __version__}
    checks: list[GateCheck] = []
    adapter_files: dict[str, object] = {}
    imports: list[dict[str, object]] = []
    for imported in brief.imports:
        try:
            source = import_source(imported.path, workspace)
            if source["system"] != imported.system:
                raise ValueError(f"expected {imported.system} import, got {source['system']}")
            imports.append(source)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            checks.append(
                check(
                    f"imports.{imported.system}.{Path(imported.path).name}",
                    "imports",
                    "unknown",
                    f"import could not be resolved: {exc}",
                )
            )
    (out_dir / "imports.json").write_text(
        json.dumps(imports, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if imports:
        adapter_files["imports"] = [
            {
                "system": entry.get("system"),
                "path": entry.get("path"),
                "sha256": entry.get("sha256"),
            }
            for entry in imports
        ]
    if "spice" in selected and brief.spice is not None:
        spice_dir = out_dir / "spice"
        result, files = run_ngspice(brief.spice.deck, workspace, spice_dir)
        checks.extend(result)
        adapter_files["spice"] = files
    if "pdn" in selected and brief.pdn is not None:
        imported_nets = _keyed_import_records(imports, "circuit", "nets", "ref")
        imported_wires = _keyed_import_records(imports, "wire", "wires", "id")
        for rail in brief.pdn.rails:
            updated_loads: list[PdnLoad] = []
            for load in rail.loads:
                if isinstance(load.current_a, str):
                    net = load.current_a.removeprefix("import:")
                    current = imported_nets.get(net, {}).get("current_a")
                    if not isinstance(current, (int, float)):
                        checks.append(
                            check(
                                f"pdn.{rail.name}.drop.{load.node}",
                                "pdn",
                                "unknown",
                                f"imported current for {net!r} is missing",
                            )
                        )
                        continue
                    updated_loads.append(load.model_copy(update={"current_a": float(current)}))
                else:
                    updated_loads.append(load)
            updated_branches: list[PdnBranch] = []
            missing_wire: str | None = None
            for branch in rail.branches:
                if branch.kind == "wire" and branch.ref.startswith("import:"):
                    wire_id = branch.ref.removeprefix("import:")
                    wire = imported_wires.get(wire_id)
                    if wire is None:
                        missing_wire = wire_id
                        break
                    length_m = _number(wire.get("length_m"))
                    resistance = _number(wire.get("resistance_ohm_per_km"))
                    ampacity = _number(wire.get("ampacity_a"))
                    if length_m is None or resistance is None or ampacity is None:
                        missing_wire = wire_id
                        break
                    updated_branches.append(
                        branch.model_copy(
                            update={
                                "length_m": length_m,
                                "resistance_ohm_per_km": resistance,
                                "ampacity_a": ampacity,
                            }
                        )
                    )
                else:
                    updated_branches.append(branch)
            if missing_wire is not None:
                checks.append(
                    check(
                        f"pdn.{rail.name}.network",
                        "pdn",
                        "unknown",
                        f"imported wire {missing_wire!r} is missing",
                    )
                )
            elif len(updated_loads) == len(rail.loads):
                checks.extend(
                    run_pdn_rail(
                        rail.model_copy(
                            update={"loads": updated_loads, "branches": updated_branches}
                        )
                    )
                )
    if "thermal" in selected and brief.thermal is not None:
        checks.extend(run_thermal(brief.thermal))
    if "wca" in selected and brief.wca is not None:
        checks.extend(run_wca(brief.wca))
        spice_outputs = [output for output in brief.wca.outputs if output.spice_measure is not None]
        if spice_outputs and brief.spice is not None and "spice" in selected:
            checks.extend(_run_spice_wca(brief, workspace, out_dir))
        elif spice_outputs:
            checks.extend(
                check(
                    f"wca.{method}.{output.name}",
                    "wca",
                    "unknown",
                    "SPICE-measure WCA requires the SPICE analysis to be selected and declared",
                )
                for output in spice_outputs
                for method in brief.wca.methods
            )
    if "emc" in selected and brief.emc is not None:
        emc = brief.emc
        imported_emc_nets = _keyed_import_records(imports, "circuit", "nets", "ref")
        interfaces = list(emc.interfaces)
        declared_connectors = {item.connector_ref for item in interfaces}
        for connector in _import_records(imports, "circuit", "connectors"):
            connector_ref = connector.get("ref")
            if isinstance(connector_ref, str) and connector_ref not in declared_connectors:
                checks.append(
                    check(
                        f"emc.interface.{connector_ref}",
                        "emc",
                        "unknown",
                        "declare the nets of this external connector",
                    )
                )
        declared_interface_nets = {net for item in interfaces for net in item.nets}
        signals: list[EmcSignal] = []
        for signal in emc.signals:
            if signal.v_max is None and signal.net in declared_interface_nets:
                imported_net = imported_emc_nets.get(signal.net)
                voltage = _number(imported_net.get("voltage_v")) if imported_net else None
                if voltage is not None:
                    signal = signal.model_copy(update={"v_max": voltage})
            signals.append(signal)
        emc = emc.model_copy(update={"signals": signals})
        checks.extend(run_emc(emc))
    if "dft" in selected and brief.dft is not None:
        dft = brief.dft
        imported_nets = _import_records(imports, "circuit", "nets")
        imported_refs = {
            str(net.get("ref") or net.get("id"))
            for net in imported_nets
            if isinstance(net.get("ref") or net.get("id"), str)
        }
        imported_power = {
            str(net.get("ref") or net.get("id"))
            for net in imported_nets
            if net.get("signal_class") == "power"
            and isinstance(net.get("ref") or net.get("id"), str)
        }
        if dft.required == "all" and imported_refs:
            dft = dft.model_copy(update={"nets": sorted(set(dft.nets) | imported_refs)})
        elif dft.required == "power_and_critical":
            dft = dft.model_copy(update={"nets": sorted(set(dft.nets) | imported_power)})
            if not imported_nets and not dft.nets:
                checks.append(
                    check(
                        "dft.power_nets",
                        "dft",
                        "unknown",
                        "power_and_critical requires declared or imported power nets",
                    )
                )
            elif not imported_nets and not brief.dft.nets:
                checks.append(
                    check(
                        "dft.power_nets",
                        "dft",
                        "unknown",
                        "no connectivity import is available to identify power nets",
                    )
                )
        checks.extend(run_dft(dft))
    if "fem" in selected and brief.fem is not None:
        checks.extend(run_calculix(brief.fem, out_dir / "fem")[0])
        adapter_files["fem"] = {"directory": str(out_dir / "fem")}
    if "rf" in selected and brief.rf is not None:
        rf = brief.rf
        data: TouchstoneData | None = None
        if rf.touchstone_path:
            try:
                touchstone_path = workspace_path(rf.touchstone_path, workspace)
                data = parse_touchstone(touchstone_path)
                adapter_files["rf"] = {"touchstone": str(touchstone_path)}
            except (OSError, ValueError) as exc:
                checks.append(
                    check("rf.touchstone", "rf", "unknown", f"Touchstone parse failed: {exc}")
                )
        elif rf.rfsim:
            data, detail = _run_rfsim(brief, workspace, out_dir)
            adapter_files["rf"] = {"rfsim": detail}
            if data is None:
                checks.append(check("rf.rfsim", "rf", "unknown", detail))
        if data is not None:
            checks.extend(_rf_checks(data, brief))
        for item in rf.microstrip:
            try:
                impedance = microstrip_impedance(
                    item.width_mm, item.height_mm, item.thickness_um, item.er
                )
            except (ArithmeticError, ValueError) as exc:
                checks.append(
                    check(
                        f"rf.microstrip.{item.name}",
                        "rf",
                        "unknown",
                        f"Hammerstad-Jensen estimate failed: {exc}",
                    )
                )
                continue
            tolerance = item.target_ohm * item.tol_pct / 100
            passed = abs(impedance - item.target_ohm) <= tolerance
            checks.append(
                check(
                    f"rf.microstrip.{item.name}",
                    "rf",
                    "pass" if passed else "fail",
                    f"Hammerstad-Jensen impedance {impedance:.9g} Ω",
                    measured=impedance,
                    limit=(
                        f"{item.target_ohm - tolerance:.9g} to {item.target_ohm + tolerance:.9g} Ω"
                    ),
                )
            )
        if (
            rf.bands
            and data is None
            and not any(item.id == "rf.touchstone" or item.id == "rf.rfsim" for item in checks)
        ):
            for band in rf.bands:
                checks.append(
                    check(
                        f"rf.band.{band.name}",
                        "rf",
                        "unknown",
                        "S-parameter data is unavailable",
                    )
                )
    if not checks:
        checks.append(
            check("simulation.selection", "simulation", "unknown", "no selected analysis sections")
        )
    reject_symlinks(out_dir)
    return write_outputs(brief, brief_path, checks, tools, out_dir, adapter_files)


def _run_spice_wca(brief: SimulationBrief, workspace: Path, out_dir: Path) -> list[GateCheck]:
    assert brief.spice is not None and brief.wca is not None
    section: WcaSection = brief.wca
    outputs = [output for output in section.outputs if output.spice_measure is not None]
    if not outputs:
        return []
    checks: list[GateCheck] = []
    for output in outputs:
        for method in section.methods:
            gate_id = f"wca.{method}.{output.name}"
            corners: list[dict[str, float]] = []
            if method == "EVA":
                count = 2 ** len(section.parameters)
                if count > min(section.max_vertices, section.spice_mc_samples):
                    checks.append(
                        check(
                            gate_id, "wca", "unknown", "SPICE corner count exceeds configured cap"
                        )
                    )
                    continue
                corners = [
                    {
                        item.name: item.nominal + sign * _wca_delta(item)
                        for item, sign in zip(section.parameters, signs, strict=True)
                    }
                    for signs in itertools.product((-1, 1), repeat=len(section.parameters))
                ]
            elif method == "MC":
                if section.mc_samples > section.spice_mc_samples:
                    checks.append(
                        check(gate_id, "wca", "unknown", "SPICE Monte Carlo sample cap exceeded")
                    )
                    continue
                rng = random.Random(section.seed)
                corners = []
                for _ in range(section.mc_samples):
                    sample_values: dict[str, float] = {}
                    for item in section.parameters:
                        delta = _wca_delta(item)
                        sample_values[item.name] = (
                            rng.gauss(item.nominal, delta / 3)
                            if item.distribution == "normal"
                            else rng.uniform(item.nominal - delta, item.nominal + delta)
                        )
                    corners.append(sample_values)
            elif method == "RSS":
                count = 1 + 2 * len(section.parameters)
                if count > section.spice_mc_samples:
                    checks.append(check(gate_id, "wca", "unknown", "SPICE RSS run cap exceeded"))
                    continue
                nominal = {item.name: item.nominal for item in section.parameters}
                corners = [nominal]
                for item in section.parameters:
                    delta = _wca_delta(item)
                    for sign in (-1, 1):
                        corner_values = dict(nominal)
                        corner_values[item.name] += sign * delta
                        corners.append(corner_values)
            else:
                checks.append(check(gate_id, "wca", "unknown", "unsupported WCA method"))
                continue
            measurements: list[float] = []
            error: str | None = None
            for index, corner in enumerate(corners):
                corner_dir = out_dir / "wca-spice" / output.name / method.lower() / f"{index:04d}"
                corner_dir.mkdir(parents=True, exist_ok=True)
                try:
                    rendered = render_deck(brief.spice.deck, workspace)
                    lines = rendered.splitlines()
                    remaining = dict(corner)
                    for line_index in range(len(lines)):
                        if not re.match(r"^\s*\.param\b", lines[line_index], re.IGNORECASE):
                            continue
                        for key, value in corner.items():
                            pattern = re.compile(
                                rf"(?i)(?<![A-Za-z0-9_]){re.escape(key)}\s*=\s*(?:\{{[^}}]*\}}|[^\s]+)"
                            )
                            updated, count = pattern.subn(f"{key}={value:.12g}", lines[line_index])
                            if count:
                                lines[line_index] = updated
                                remaining.pop(key, None)
                    end_indexes = [
                        i for i, line in enumerate(lines) if line.strip().lower() == ".end"
                    ]
                    insertion = end_indexes[-1] if end_indexes else len(lines)
                    if remaining:
                        lines.insert(
                            insertion,
                            ".param "
                            + " ".join(f"{key}={value:.12g}" for key, value in remaining.items()),
                        )
                    deck_path = corner_dir / "deck.cir"
                    deck_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    result = subprocess.run(
                        [
                            os.environ.get("SIM_NGSPICE", "ngspice"),
                            "-b",
                            "-o",
                            "run.log",
                            "deck.cir",
                        ],
                        cwd=corner_dir,
                        capture_output=True,
                        text=True,
                        timeout=brief.spice.deck.timeout_s,
                        check=False,
                    )
                    reject_symlinks(out_dir)
                    log = (
                        (corner_dir / "run.log").read_text(encoding="utf-8", errors="replace")
                        if (corner_dir / "run.log").is_file()
                        else ""
                    )
                    parsed = parse_measures(
                        log + result.stdout + result.stderr,
                        brief.spice.deck,
                        result.returncode,
                    )
                    target = next(
                        (item for item in parsed if item.id == f"spice.{output.spice_measure}"),
                        None,
                    )
                    if target is None or target.measured is None:
                        error = f"corner {index} did not produce measure {output.spice_measure}"
                        break
                    measurements.append(target.measured)
                except (OSError, subprocess.SubprocessError, ValueError) as exc:
                    error = f"corner {index} failed: {exc}"
                    break
            if error:
                checks.append(check(gate_id, "wca", "unknown", error))
                continue
            if method == "RSS":
                variance = sum(
                    ((measurements[index + 2] - measurements[index + 1]) / 2) ** 2
                    for index in range(0, len(measurements) - 1, 2)
                )
                spread = math.sqrt(variance)
                low, high = measurements[0] - spread, measurements[0] + spread
            else:
                low, high = min(measurements), max(measurements)
            if output.min is None and output.max is None:
                checks.append(
                    check(
                        gate_id,
                        "wca",
                        "unknown",
                        "WCA output has no acceptance bounds",
                        measured=low,
                    )
                )
                continue
            passed = (output.min is None or low >= output.min) and (
                output.max is None or high <= output.max
            )
            checks.append(
                check(
                    gate_id,
                    "wca",
                    "pass" if passed else "fail",
                    f"SPICE corner range [{low:.9g}, {high:.9g}]",
                    measured=low,
                    limit=f"min {output.min}; max {output.max}; measured_max {high:.9g}",
                )
            )
    return checks
