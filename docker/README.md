# Simulation images

`sim-tools` contains the base deterministic environment (Python 3.12,
ngspice, and CalculiX). `sim-tools-em` adds openEMS/CSXCAD and the pinned
KiCad-rfsim runner. Both images use the Debian base digest; solver source
revisions and runtime packages are documented in [operations](../docs/operations.md).

Build the base image and run the example smoke:

```bash
docker build --target sim-tools -f docker/sim-tools.Dockerfile -t sim-tools:local .
python scripts/smoke_image.py --image sim-tools:local
```

The smoke script retains its stopped containers and prints their names.

The optional openEMS target is a source build and may take substantially
longer. Do not work around a non-trivial build failure without reviewing and
documenting the change.

`image-digests.json` reserves entries for published image references. Local
build tags are not published digests and must not be recorded as such.
