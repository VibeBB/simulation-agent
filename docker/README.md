# Simulation images

`sim-tools` contains the base deterministic environment (Python 3.12,
ngspice, and CalculiX). `sim-tools-em` adds openEMS/CSXCAD and the pinned
KiCad-rfsim runner. Both build stages use Ubuntu 24.04 (Noble), pinned to
`sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3`.
The image uses Noble because Debian Trixie has no `calculix-ccx` installation
candidate; it only publishes the `calculix-ccx-test` documentation package
(`2.22-1`), which recommends the unavailable solver package. Noble's observed
apt candidates were `calculix-ccx` `2.21-1` and `ngspice`
`42+ds-3build1`. Runtime package names and versions are documented in
[operations](../docs/operations.md).

Build the base image and run the example smoke:

```bash
docker build --target sim-tools -f docker/sim-tools.Dockerfile -t sim-tools:local .
python scripts/smoke_image.py --image sim-tools:local
```

The smoke script retains its stopped containers and prints their names.

The optional openEMS target is a source build and may take substantially
longer. Do not work around a non-trivial build failure without reviewing and
documenting the change.

CMake installs the openEMS and CSXCAD C++ libraries but not their Python
interfaces. The image builds those interfaces from the pinned
`CSXCAD/python` and `openEMS/python` source directories with Noble's
`cython3` `3.0.8-1ubuntu3`, and checks them with the system interpreter
`/usr/bin/python3`. The tested interfaces report CSXCAD `0.7.0` and openEMS
`0.37.0`.

`image-digests.json` reserves entries for published image references. Local
build tags are not published digests and must not be recorded as such.
