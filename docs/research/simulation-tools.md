# Simulation tool research (2026-09)

Survey of the external solvers the `sim` plugin integrates, with the
decision taken for v0.1. Versions and licences were checked against the
upstream project pages and Debian trackers in September 2026.

| Domain | Tool | Latest upstream | Packaged | Licence | v0.1 decision |
|---|---|---|---|---|---|
| Circuit (SPICE) | ngspice | 47 (2026-08-11) | Debian trixie 44.2, trixie-backports / testing 47, Ubuntu Noble 42+ds-3build1 | BSD-3-Clause (+ some modified-BSD / public-domain parts) | Batch subprocess `ngspice -b`; `.meas` results parsed from the log |
| Circuit (SPICE) | PySpice | 1.5 | PyPI | GPL-3.0 | **Rejected**: GPL import into a BSD package; we only need batch mode |
| Netlist source | `kicad-cli sch export netlist --format spice` | KiCad 10/11 | KiCad | GPL-3.0 (tool only) | Accepted as an *input file*; sim never links KiCad |
| PDN / IR drop | padne (2.5D FEM Laplace, KiCad-native) | master | pipx / binary | GPL-3.0 | Optional subprocess adapter later; v0.1 ships a deterministic resistive-network solver |
| PDN / IR drop | KiPIDA (KiCad DC PI plugin) | 2026 | KiCad PCM | see upstream | Reference only (GUI plugin, not scriptable in CI) |
| Thermal resistance | built-in θ-network | — | — | BSD (ours) | Nodal solve of junction/case/board/ambient networks; Tj predicates |
| WCA | built-in EVA / RSS / Monte Carlo | — | — | BSD (ours) | Expression models and ngspice corner runs |
| EMC / ESD | built-in design predicates | — | — | BSD (ours) | IEC 61000-4-2 level, TVS Vrwm/Vclamp, placement, decoupling, critical length |
| FEM | CalculiX CrunchiX (ccx) | 2.23 | Debian trixie: no `calculix-ccx` candidate (only `calculix-ccx-test` 2.22-1); Ubuntu Noble `calculix-ccx` 2.21-1 | GPL-2.0-or-later | Generate `.inp` in Python, run unmodified `ccx` as subprocess, parse `.dat`; Docker follows Noble CI |
| Meshing | gmsh | 4.15.2 | PyPI / Debian | GPL-2.0-or-later | Not needed for v0.1 (structured hex mesh generated in Python) |
| DFT | built-in gate | — | — | BSD (ours) | Test-point coverage, probe pitch/pad size, debug header, boundary scan |
| RF / EM | openEMS (FDTD) + CSXCAD | v0.0.36 stable, v0.37.0-rc1 (2026-06) | **Removed from Debian** (last 0.0.35 in bookworm) | GPL-3.0 (openEMS), LGPL-3.0 (CSXCAD) | Built from source in an optional image target; subprocess only |
| RF / EM | KiCad-rfsim (NBalciunas) | main, KiCad 10 | KiCad PCM ZIP | MIT | Its headless `runner.py model.json out/` is run as a subprocess; results read from `results.sNp` |
| RF / EM | kicad_openems_pipeline, pcbmodelgen | — | GitHub | see upstream | Reference only |
| Touchstone | scikit-rf | 1.11.0 | PyPI | BSD-3-Clause | Not needed; a stdlib Touchstone v1 parser is sufficient for S-parameter predicates |

## Notes per tool

### ngspice
- Batch mode (`ngspice -b -o run.log deck.cir`) prints `.meas` results as
  `name = value` lines; a failed measurement prints `failed`, which the
  adapter must map to `unknown`, never to a number.
- Shared-library mode (`libngspice`) is faster but needs ctypes/cffi
  bindings; batch mode keeps the process boundary that the family uses for
  every external tool.
- ngspice 47 adds PSS updates and small-signal noise for code models;
  nothing in v0.1 depends on 45+ features, so the Debian/Ubuntu packages
  are acceptable.

### CalculiX
- Abaqus-like `.inp` input. `*NODE PRINT` / `*EL PRINT` write plain-text
  tables to `<job>.dat`, which is much simpler to parse than `.frd`.
- GPL-2.0-or-later: executed unmodified as a separate process, never
  linked or vendored (same rule as mechanical-agent).
- The pinned Debian Trixie repositories expose `calculix-ccx-test` `2.22-1`
  (documentation/tests) but no solver candidate for `calculix-ccx`; that test
  package recommends the unavailable solver. Ubuntu Noble provides
  `calculix-ccx` `2.21-1`, so the Docker base follows CI rather than building
  a solver from source. Upstream 2.23 is ahead of that package; the element
  types used here (C3D20R / C3D8) are stable across these versions.

### openEMS / KiCad-rfsim
- openEMS was dropped from Debian (tracker: "package is gone", RFP open),
  so the image builds `openEMS-Project` from a pinned tag.
- The `v0.37.0-rc1` source build at `92b82520054a62201ac69bd905fdf2533810367f`
  installs the C++ libraries but not the Python interfaces. The image builds
  the interfaces from `CSXCAD/python` and `openEMS/python` with Noble's
  `cython3` `3.0.8-1ubuntu3`; the tested packages are CSXCAD `0.7.0` and
  openEMS `0.37.0`, imported by `/usr/bin/python3`.
- KiCad-rfsim is a KiCad 10 plugin. Its GUI extracts board geometry into
  `model.json`; the separate `runner.py` imports only numpy, CSXCAD and
  openEMS and can run headless: `python runner.py model.json output_dir`.
  It writes `results.sNp`, `lines.json` and `farfield_pN.json`.
- Upstream warns that CPW and stripline ports on openEMS v0.37.0-rc1 give
  20-50 % low impedance; the sim gate therefore treats S-parameter
  results as `unknown` when passivity is violated (|S| > 1).

### PDN / IR drop
- padne solves the Laplace equation on real copper from a KiCad project
  and is the best open option for plane-level IR drop, but it needs the
  KiCad Python bindings and a Qt stack. v0.1 uses a declared resistive
  network (traces, planes as sheet-resistance segments, vias, connectors,
  harness wires from wire-agent contracts) solved by nodal analysis.
  Copper resistivity is 1.724e-8 ohm*m at 20 C with alpha = 0.00393 /K.
- Trace current capacity uses IPC-2221 (I = k * dT^0.44 * A^0.725, k =
  0.048 external / 0.024 internal, A in mil^2) as a conservative
  predicate; IPC-2152 charts are not machine-readable.

## Sources
- https://ngspice.sourceforge.io/news.html
- https://tracker.debian.org/pkg/ngspice
- https://www.dhondt.de/
- https://tracker.debian.org/pkg/calculix-ccx
- https://github.com/thliebig/openEMS-Project/releases
- https://tracker.debian.org/pkg/openems
- https://docs.openems.de/en/latest/concepts/simulation.html
- https://github.com/NBalciunas/kicad-rfsim
- https://github.com/atx/padne
- https://github.com/oskarvh/kicad_openems_pipeline
- https://github.com/jcyrax/pcbmodelgen
- https://pypi.org/project/gmsh/
- https://github.com/PySpice-org/PySpice
- https://github.com/scikit-rf/scikit-rf
- https://docs.kicad.org/7.0/en/cli/cli.html
