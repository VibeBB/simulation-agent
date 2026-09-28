"""CalculiX input generation and conservative output extraction."""

from __future__ import annotations

import math
import os
import re
import subprocess
from pathlib import Path

from ..analysis import run_fem_analytic
from ..brief import FemSection
from ..gates import GateCheck, check
from ..workspace import reject_symlinks


def _element_lines(elements: list[tuple[int, list[int]]]) -> list[str]:
    lines: list[str] = []
    for element_id, connectivity in elements:
        entries = [element_id, *connectivity]
        lines.extend(
            ", ".join(str(value) for value in entries[start : start + 16])
            for start in range(0, len(entries), 16)
        )
    return lines


def _node_set_lines(name: str, node_ids: list[int]) -> list[str]:
    return [
        f"*NSET, NSET={name}",
        *(
            ", ".join(str(value) for value in node_ids[start : start + 16])
            for start in range(0, len(node_ids), 16)
        ),
    ]


def generate_input(section: FemSection, job: str = "fem") -> str:
    geometry, mesh = section.geometry, section.mesh
    nx, ny, nz = mesh.nx, mesh.ny, mesh.nz
    node_ids: dict[tuple[int, int, int], int] = {}
    nodes: list[tuple[int, float, float, float]] = []

    def node(i: int, j: int, k: int) -> int:
        key = (i, j, k)
        if key not in node_ids:
            node_id = len(node_ids) + 1
            node_ids[key] = node_id
            nodes.append(
                (
                    node_id,
                    geometry.length_mm * i / (2 * nx),
                    geometry.width_mm * j / (2 * ny),
                    geometry.height_mm * k / (2 * nz),
                )
            )
        return node_ids[key]

    elements: list[tuple[int, list[int]]] = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                x0, x1 = 2 * i, 2 * (i + 1)
                y0, y1 = 2 * j, 2 * (j + 1)
                z0, z1 = 2 * k, 2 * (k + 1)
                corners = [
                    (x0, y0, z0),
                    (x1, y0, z0),
                    (x1, y1, z0),
                    (x0, y1, z0),
                    (x0, y0, z1),
                    (x1, y0, z1),
                    (x1, y1, z1),
                    (x0, y1, z1),
                ]
                connectivity = [node(*point) for point in corners]
                if mesh.element == "C3D20R":
                    mids = [
                        (x0 + 1, y0, z0),
                        (x1, y0 + 1, z0),
                        (x0 + 1, y1, z0),
                        (x0, y0 + 1, z0),
                        (x0 + 1, y0, z1),
                        (x1, y0 + 1, z1),
                        (x0 + 1, y1, z1),
                        (x0, y0 + 1, z1),
                        (x0, y0, z0 + 1),
                        (x1, y0, z0 + 1),
                        (x1, y1, z0 + 1),
                        (x0, y1, z0 + 1),
                    ]
                    connectivity.extend(node(*point) for point in mids)
                elements.append((len(elements) + 1, connectivity))
    fixed = [node_id for node_id, x, _y, _z in nodes if math.isclose(x, 0)]
    tip = [node_id for node_id, x, _y, _z in nodes if math.isclose(x, geometry.length_mm)]
    element_type = mesh.element
    total_force = -section.load.force_n
    # Apply a uniform force to every generated tip-face node.
    per_node_force = total_force / len(tip)
    lines = [
        "*NODE",
        *(f"{node_id}, {x:.9g}, {y:.9g}, {z:.9g}" for node_id, x, y, z in nodes),
        f"*ELEMENT, TYPE={element_type}, ELSET=EALL",
        *_element_lines(elements),
        *_node_set_lines("FIXED", fixed),
        *_node_set_lines("TIP", tip),
        *_node_set_lines("NALL", list(node_ids.values())),
        "*MATERIAL, NAME=MAT",
        "*ELASTIC",
        f"{section.material.youngs_mpa:.9g}, {section.material.poisson:.9g}",
        "*SOLID SECTION, ELSET=EALL, MATERIAL=MAT",
        "*STEP",
        "*STATIC",
        "*BOUNDARY",
        "FIXED, 1, 3, 0",
        "*CLOAD",
        *(f"{node_id}, 3, {per_node_force:.12g}" for node_id in tip),
        "*NODE PRINT, NSET=NALL",
        "U",
        "*NODE PRINT, NSET=TIP",
        "U",
        "*EL PRINT, ELSET=EALL",
        "S",
        "*END STEP",
    ]
    return "\n".join(lines) + "\n"


def parse_dat(text: str) -> tuple[float | None, float | None, float | None]:
    displacements: list[float] = []
    tip_displacements: list[float] = []
    stresses: list[float] = []
    in_stress = False
    in_tip = False
    for line in text.splitlines():
        lowered = line.lower()
        if "displacements" in lowered or "displacement" in lowered:
            in_stress = False
            in_tip = bool(re.search(r"\bset\s+tip\b", lowered))
        elif "stresses" in lowered or "stress" in lowered:
            in_stress = True
            in_tip = False
        numbers = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", line)
        if len(numbers) >= 4:
            try:
                values = [float(item) for item in numbers]
            except ValueError:
                continue
            if values[0].is_integer() and not in_stress:
                displacements.append(abs(values[3]))
                if in_tip:
                    tip_displacements.append(values[3])
            elif in_stress and len(values) >= 7:
                s1, s2, s3, t12, t23, t31 = values[-6:]
                vm = math.sqrt(
                    max(
                        0.0,
                        0.5 * ((s1 - s2) ** 2 + (s2 - s3) ** 2 + (s3 - s1) ** 2)
                        + 3 * (t12**2 + t23**2 + t31**2),
                    )
                )
                stresses.append(vm)
    return (
        max(displacements) if displacements else None,
        abs(sum(tip_displacements) / len(tip_displacements)) if tip_displacements else None,
        max(stresses) if stresses else None,
    )


def run_calculix(section: FemSection, out_dir: Path) -> tuple[list[GateCheck], dict[str, object]]:
    try:
        reject_symlinks(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        reject_symlinks(out_dir)
    except (OSError, ValueError) as exc:
        reason = f"unsafe CalculiX output directory: {exc}"
        return [
            check("fem.safety_factor", "fem", "unknown", reason),
            check("fem.deflection", "fem", "unknown", reason),
            check("fem.cross_check", "fem", "unknown", reason),
        ], {}
    job = "simulation"
    inp = out_dir / f"{job}.inp"
    inp.write_text(generate_input(section, job), encoding="utf-8")
    analytic = run_fem_analytic(section)
    binary = os.environ.get("SIM_CCX", "ccx")
    try:
        completed = subprocess.run(
            [binary, "-i", job],
            cwd=out_dir,
            capture_output=True,
            text=True,
            timeout=section.timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        reason = f"CalculiX unavailable or timed out: {exc}"
        return [
            check("fem.safety_factor", "fem", "unknown", reason, evidence=[str(inp)]),
            check("fem.deflection", "fem", "unknown", reason),
            check("fem.cross_check", "fem", "unknown", reason),
            *analytic,
        ], {"input": str(inp)}
    try:
        reject_symlinks(out_dir)
    except (OSError, ValueError) as exc:
        reason = f"unsafe CalculiX generated output: {exc}"
        return [
            check("fem.safety_factor", "fem", "unknown", reason),
            check("fem.deflection", "fem", "unknown", reason),
            check("fem.cross_check", "fem", "unknown", reason),
            *analytic,
        ], {"input": str(inp)}
    dat_path = out_dir / f"{job}.dat"
    if completed.returncode != 0 or not dat_path.is_file():
        reason = f"CalculiX exit {completed.returncode}; expected job.dat is missing"
        return [
            check("fem.safety_factor", "fem", "unknown", reason),
            check("fem.deflection", "fem", "unknown", reason),
            check("fem.cross_check", "fem", "unknown", reason),
            *analytic,
        ], {"input": str(inp), "returncode": completed.returncode}
    deflection, tip_deflection, stress = parse_dat(
        dat_path.read_text(encoding="utf-8", errors="replace")
    )
    results: list[GateCheck] = []
    if stress is None:
        results.append(
            check("fem.safety_factor", "fem", "unknown", "no integration-point stress parsed")
        )
    else:
        safety_factor = section.material.yield_mpa / stress
        results.append(
            check(
                "fem.safety_factor",
                "fem",
                "pass" if safety_factor >= section.limits.min_safety_factor else "fail",
                f"CalculiX safety factor {safety_factor:.9g}",
                measured=safety_factor,
                limit=f"≥ {section.limits.min_safety_factor:.9g}",
                evidence=[str(dat_path)],
            )
        )
    if deflection is None:
        if section.limits.max_deflection_mm is not None:
            results.append(check("fem.deflection", "fem", "unknown", "no displacement parsed"))
        results.append(check("fem.cross_check", "fem", "unknown", "no displacement parsed"))
    else:
        limit = section.limits.max_deflection_mm
        if limit is not None:
            results.append(
                check(
                    "fem.deflection",
                    "fem",
                    "pass" if deflection <= limit else "fail",
                    f"maximum absolute z displacement {deflection:.9g} mm",
                    measured=deflection,
                    limit=f"≤ {limit:.9g} mm",
                )
            )
        g = section.geometry
        beam_delta = (
            section.load.force_n
            * (g.length_mm / 1000) ** 3
            / (
                3
                * section.material.youngs_mpa
                * 1e6
                * (g.width_mm / 1000)
                * (g.height_mm / 1000) ** 3
                / 12
            )
            * 1000
        )
        if tip_deflection is None:
            results.append(
                check("fem.cross_check", "fem", "unknown", "tip-set displacement is missing")
            )
        else:
            ratio = abs(tip_deflection - beam_delta) / beam_delta if beam_delta else math.inf
            results.append(
                check(
                    "fem.cross_check",
                    "fem",
                    "unknown"
                    if g.length_mm / g.height_mm < 5
                    else ("pass" if ratio <= section.cross_check_tolerance else "fail"),
                    f"tip-face mean versus beam relative difference {ratio:.9g}",
                    measured=ratio if math.isfinite(ratio) else None,
                    limit=f"≤ {section.cross_check_tolerance:.9g}",
                )
            )
    return [*results, *analytic], {
        "input": str(inp),
        "data": str(dat_path),
        "returncode": completed.returncode,
    }
