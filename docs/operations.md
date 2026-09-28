# Operations

## Runtime configuration

The CLI workspace is `OPENHANDS_PROJECT_DIR`, falling back to the current
directory. Relative input and output paths must resolve within that workspace.
Paths that traverse symlinks are rejected.
The plugin launcher accepts `SIM_LAUNCH_MODE=auto|docker|host` (default `auto`)
and `SIM_TOOLS_IMAGE`. Auto mode uses Docker only when Docker and an image
reference are available; host mode runs the package from the resolved source
tree and reports missing solver tools as `unknown`.

| Variable | Purpose |
| --- | --- |
| `SIM_NGSPICE` | ngspice executable override |
| `SIM_CCX` | CalculiX executable override |
| `SIM_OPENEMS_PYTHON` | Python interpreter containing openEMS/CSXCAD |
| `SIM_RFSIM_RUNNER` | KiCad-rfsim `runner.py` override |
| `SIM_REQUIRED_TOOLS` | Comma-separated tool names required by strict doctor |
| `SIM_SRC` | Source tree override used by host and Docker launch |

`sim doctor` always reports tool availability. `--strict` exits non-zero when
a required tool is missing. `--warn` is used by the OpenHands session-start
hook so an unavailable optional image does not block a session.

## Docker images

`sim-tools` is based on Ubuntu 24.04 (Noble), pinned by digest
`sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3`.
Both Docker stages use this same `BASE_IMAGE`. Noble ships Python 3.12 and
provides `calculix-ccx` `2.21-1` and `ngspice` `42+ds-3build1`, matching the
Ubuntu 24.04 CI verification environment. The build-time sync excludes
development and SDK-check groups. Its build-time doctor requires only
`ngspice,ccx`; the standard host doctor additionally reports optional RF tools.
APT package revisions are resolved from Ubuntu repositories during image
builds, so the base digest is pinned but APT resolution is not a byte-for-byte
lock.

The openEMS build and runtime package candidates observed on Noble included
`build-essential` `12.10ubuntu1`, `cmake` `3.28.3-1build7`, `libcgal-dev`
`5.6-1build3`, `libboost-all-dev` `1.83.0.1ubuntu2`, `libfftw3-dev`
`3.3.10-1ubuntu3`, `libhdf5-dev` `1.10.10+repack-3.1ubuntu4`,
`libopenmpi-dev` `4.1.6-7ubuntu2`, `libreadline-dev` `8.2-4build1`,
`libtinyxml-dev` `2.6.2-6.1`, `libvtk9-dev`
`9.1.0+really9.1.0+dfsg2-7.1build3`, `libxml2-dev`
`2.9.14+dfsg-1.3ubuntu3.9`, `python3-dev` `3.12.3-0ubuntu2.1`,
`python3-numpy` `1:1.26.4+ds-6ubuntu1`, `python3-h5py` `3.10.0-1ubuntu3`,
`python3-pip` `24.0+dfsg-1ubuntu1.3`, `python3-setuptools`
`68.1.2-2ubuntu1.2`, `cython3` `3.0.8-1ubuntu3`, and `swig`
`4.2.0-2ubuntu1`. The corresponding runtime candidates were
Boost filesystem/program-options/thread `1.83.0-2.1ubuntu3.2`, FFTW double
`3.3.10-1ubuntu3`, HDF5 `1.10.10+repack-3.1ubuntu4`, OpenMPI
`4.1.6-7ubuntu2`, readline `8.2-4build1`, TinyXML `2.6.2-6.1`, and VTK
`9.1.0+really9.1.0+dfsg2-7.1build3`. Their runtime package names are
`libboost-filesystem1.83.0`, `libboost-program-options1.83.0`,
`libboost-thread1.83.0`, `libfftw3-double3`, `libhdf5-103-1t64`,
`libopenmpi3t64`, `libreadline8t64`,
`libtinyxml2.6.2v5`, and `libvtk9.1t64`.

`sim-tools-em` adds openEMS/CSXCAD and KiCad-rfsim. The current build pin is
openEMS-Project v0.37.0-rc1, commit
`92b82520054a62201ac69bd905fdf2533810367f`. This release candidate is used
instead of stable v0.0.36 because the pinned KiCad-rfsim runner contains
version-gated model features requiring the newer `LEtype` behavior. The
KiCad-rfsim source is pinned to `efa0ea9bd34b13f7819c6f2d4c02e78d34b116c3`
(tree `3c6f546a77f0f2744f809e9ff090a6ec7a2e7e2e`). Do not update these
references without reviewing the runner's feature requirements and recording
the decision here.

The CMake install does not create the Python bindings, so the image also
builds them from the tag's `CSXCAD/python` and `openEMS/python` directories.
They are imported by the system interpreter `/usr/bin/python3` (CSXCAD
`0.7.0`, openEMS `0.37.0` in the tested build); the application itself uses
the locked uv environment.

Build and smoke-test locally:

```bash
docker build --target sim-tools -f docker/sim-tools.Dockerfile -t sim-tools:local .
uv run python scripts/smoke_image.py --image sim-tools:local
docker build --target sim-tools-em -f docker/sim-tools.Dockerfile -t sim-tools-em:local .
```

The base-image smoke check leaves its named containers stopped for inspection
and reuse.

The optional openEMS build is intentionally attempted only after the base
image passes. If it exceeds 60 minutes or fails for a non-trivial reason, stop
and report the exact error rather than applying an unreviewed workaround.

## Outputs and evidence

Reports are generated in `out/<name>/`; never edit them directly. `manifest.json`
hashes generated files, and `provenance.json` records the brief hash, import
hashes, tool versions, and a UTC timestamp. Keep authored inputs and generated
outputs distinct.
