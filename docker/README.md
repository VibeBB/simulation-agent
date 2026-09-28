# Simulation images

`sim-tools` contains the base deterministic environment (Python 3.12,
ngspice, and CalculiX). `sim-tools-em` adds openEMS/CSXCAD and the pinned
KiCad-rfsim runner. Both build stages use
`docker.io/library/ubuntu:26.04` (Resolute), pinned to
`sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78`.
Resolute is used because Debian Trixie has no `calculix-ccx` installation
candidate; it only publishes the `calculix-ccx-test` documentation package
(`2.22-1`), which recommends the unavailable solver package. Resolute's
observed apt versions are `calculix-ccx` `2.21-1build1`, ngspice
`45.2+ds-1`, and system Python `3.14.3-0ubuntu2`. Runtime package names and
versions are documented in
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
`CSXCAD/python` and `openEMS/python` source directories with Resolute's
system Python `3.14.3` and `cython3` `3.1.6+dfsg-1ubuntu2`, and checks them
with `/usr/bin/python3`. The tested interfaces report CSXCAD `0.7.0` and
openEMS `0.37.0`; the separate simulation package remains in its uv-managed
Python `3.12.14` environment.

`image-digests.json` reserves entries for published image references. Local
build tags are not published digests and must not be recorded as such.
