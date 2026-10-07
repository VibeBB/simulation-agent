# Third-Party Notices

`simulation-agent` is licensed under the BSD 3-Clause License (see
`LICENSE`). The `sim-tools` image and the development environment install
or invoke the components below. All are unmodified executables or
subprocesses; none is import-linked into `sim` (ADR-0001: subprocess-only
solvers).

| Component | Version pin | License | Use |
|---|---|---|---|
| Ubuntu 26.04 (Resolute) | `ubuntu:26.04@sha256:da6fc2be…` | various | Base image |
| uv | `ghcr.io/astral-sh/uv:0.12.23` | Apache-2.0 / MIT | Python and package manager |
| CPython | 3.12.x via uv / system | PSF-2.0 | Runtime |
| ngspice | Ubuntu `ngspice-45.2` | BSD-3-Clause | SPICE analysis (`.meas` batch runs) |
| CalculiX (`calculix-ccx`) | Ubuntu `2.21-1build1` | GPL-2.0 | FEM solver subprocess |
| openEMS + CSXCAD | commit `81f32e03d514f270e679b63e8861d24eaa03a7e2` | GPL-3.0 | Optional FDTD EM field solver |
| KiCad-rfsim | commit `efa0ea9bd34b13f7819c6f2d4c02e78d34b116c3` | GPL-3.0 | Optional RF/microstrip modelling |
| pydantic | `>=2` via `uv.lock` | MIT | Contract models |
| mcp | `>=1.29,<2` via `uv.lock` | MIT | MCP server |
| openhands-sdk / openhands-tools | `1.53.0` (sdk-check group) | MIT | Plugin-load verification |
| coverage | `7.16.2` (dev group) | Apache-2.0 | Test coverage measurement |
| pytest-cov | `7.1.0` (dev group) | MIT | Pytest coverage integration |

Ubuntu package versions above are those measured in the 2026-10-04 image
rebuild (recorded in `docker/image-digests.json`); packages resolve from
the repositories for the digest-pinned Ubuntu 26.04 base. Resolute is
used because Debian Trixie has no `calculix-ccx` installation candidate.

Sources: openEMS <https://github.com/thliebig/openEMS-Project>; KiCad-rfsim
<https://github.com/NBalciunas/kicad-rfsim>; ngspice
<https://ngspice.sourceforge.io>; CalculiX <https://www.calculix.de>. GPL
sources for Ubuntu packages are available from the Ubuntu archive
(`apt-get source <package>`); the openEMS build records its pinned commit
in the Dockerfile (`OPENEMS_COMMIT`).
