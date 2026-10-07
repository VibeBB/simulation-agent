# Solver sid-.deb adoption: ngspice 47, CalculiX 2.23

Reviewed 2026-10-07 while replacing the resolute apt solver packages
(`ngspice 45.2+ds-1`, `calculix-ccx 2.21-1build1`) with checksum-pinned
Debian unstable `.debs` (`ngspice_47+ds-1_amd64.deb`,
`calculix-ccx_2.23-1_amd64.deb`) fetched from `snapshot.debian.org`.

## ngspice 45.2 -> 47 (46 skipped)

Reviewed the ngspice-47 release notes (2026-08-11) plus the intervening
ngspice-46 changes.

Adopted implicitly — the deterministic `.meas`-style batch analyses get
more accurate models and devices without contract changes:

- Periodic steady-state (PSS) analysis update.
- Small-signal noise analysis extended to XSPICE code models.
- VDMOS soft-recovery body diode; dc-sweep capacitance support for
  HFET/MEASFET/VDMOS plus BJT/VBIC/HICUM capacitance fixes.
- `newcompat.ki` maps `/gnd` to node `0` (netlist portability).
- ISRC pwl gains `td`/`r` parameters; new behavioral capacitor.
- `adc_bridge`/`dac_bridge` multi-bit and Schmitt-trigger refinements;
  TSTEP/TSTOP XSPICE macros; SEEgenerator update.
- Memory-usage probing on all OSes; engineering-notation exponent
  printing; `2n`/`5m` filesource notation.
- `.sndprint`/`.sndparam` audio I/O; `pyplot` matplotlib command.

Not adopted, with reasons:

- `pyplot` and audio I/O are interactive/desktop affordances; sim
  analyses run batch + deterministic PNG plots and never invoke plotting
  commands.
- Paranoia_Parallel test suite is upstream's own CI harness.

## CalculiX 2.21 -> 2.23

Reviewed the CalculiX 2.23 changelog (dhondt.de).

Adopted implicitly — solver corrections and keyword coverage the FEM
runner emits transparently:

- Submodels extended to heat transfer; axisymmetric-to-3D submodel
  boundary conditions; `*EQUATION` allows a node set as first term.
- New `*DAMAGE INITIATION` keyword; C3D8I element correction.
- `*REFINE MESH,SMOOTHING ONLY` keeps original node numbering.
- Composite shells in `*HEAT TRANSFER`; linear temperature fields on
  `*TEMPERATURE`/`*BOUNDARY`; contact inside `*CYCLIC SYMMETRY MODEL`.
- cgx additions (`comp e`/`p`/`capt`/`ulin`, `test i` + PENTR) are not
  adopted — cgx is not shipped in the image.

## Provenance and tracking

Both `.debs` are Debian *unstable* builds installed on Ubuntu 26.04.
Their `Depends` all resolve from resolute (ngspice: libreadline8t64,
libxaw7, libxft2, libsamplerate0, libsndfile1, libxt6t64, …; ccx:
libarpack2t64, libblas3, liblapack3, libgfortran5, libspooles2.2t64);
sid itself is never added to `sources.list`. Because sid builds sit
outside the Ubuntu security tracker, both pins are registered as
`docker-deb` targets in `scripts/check_dependency_updates.py` so newer
sid uploads surface in the weekly dependency report.

The CI runner-side `sudo apt-get install ngspice calculix-ccx` used by
the real-solver `tools`-marker tests still installs the resolute
versions (45.2 / 2.21); the tests are version-agnostic contract checks,
and keeping the runner on apt deliberately exercises the adapters
against a *different* solver version than the image pins — divergence is
a feature for parser robustness.
