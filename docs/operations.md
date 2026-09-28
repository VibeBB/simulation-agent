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

`sim-tools` is based on Debian 13 slim pinned by digest
`sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a`.
It contains Python 3.12, ngspice, CalculiX, and the package. Its build-time
sync excludes development and SDK-check groups. Its build-time doctor
requires only `ngspice,ccx`; the standard host doctor additionally
reports optional RF tools.
APT package revisions are resolved from Debian repositories during image
builds; the base image and solver source commits are pinned, but APT resolution
is not a byte-for-byte lock.

`sim-tools-em` adds openEMS/CSXCAD and KiCad-rfsim. The current build pin is
openEMS-Project v0.37.0-rc1, commit
`92b82520054a62201ac69bd905fdf2533810367f`. This release candidate is used
instead of stable v0.0.36 because the pinned KiCad-rfsim runner contains
version-gated model features requiring the newer `LEtype` behavior. The
KiCad-rfsim source is pinned to `efa0ea9bd34b13f7819c6f2d4c02e78d34b116c3`
(tree `3c6f546a77f0f2744f809e9ff090a6ec7a2e7e2e`). Do not update these
references without reviewing the runner's feature requirements and recording
the decision here.

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
