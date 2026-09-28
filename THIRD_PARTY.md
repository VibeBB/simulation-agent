# Third-party software and attribution

No third-party source code is vendored. The tools below are installed in or
invoked by the optional simulation images as unmodified separate processes.

| Component | Licence | Use |
| --- | --- | --- |
| ngspice | BSD-3-Clause and upstream component notices | Batch SPICE solver |
| CalculiX / ccx | GPL-2.0-or-later | Finite-element subprocess |
| openEMS | GPL-3.0 | Optional RF electromagnetic subprocess |
| CSXCAD | LGPL-3.0 | Optional openEMS geometry/runtime dependency |
| KiCad-rfsim | MIT | Pinned headless model runner |

All simulation-agent source is licensed under the repository's BSD-3-Clause
license. Do not import-bind or modify the solver processes.
