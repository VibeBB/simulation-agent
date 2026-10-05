# Commands

Commands live under `plugins/sim/commands/` and are invoked as `/sim:<name>`
in OpenHands; each shells out to `sim_launcher.py`, which runs the matching
`python -m sim` subcommand inside the pinned `sim-tools` Docker image.

| Command | Effect |
| --- | --- |
| `/sim:doctor` | report solver/tool availability (`--strict` to require one) |
| `/sim:run <brief>` | validate and run every declared analysis; writes `out/<name>/` |
| `/sim:gates <brief>` | aggregate gate verdict summary for a brief |
| `/sim:import <file> --brief <brief>` | mirror a sister contract into `imports[]` + `imports.json` |
| `/sim:respond <request.sim-request.json>` | answer a v1 sister request; writes `*.sim-response.json` |
| `/sim:spice` | run only the SPICE section |
| `/sim:pdn` | run only the PDN section |
| `/sim:thermal` | run only the thermal section |
| `/sim:wca` | run only the WCA section |
| `/sim:emc` | run only the EMC section |
| `/sim:dft` | run only the DFT section |
| `/sim:fem` | run only the FEM section |
| `/sim:rf` | run only the RF section |
| `/sim:records` | append a decision/impression/vision-review record or show `record status` |
| `/sim:ux-inbox` | list SLP v2 liaison requests and malformed files |
| `/sim:plots <out_dir>` | list an out dir's plots for inline viewing; record a vision review per plot |

Equivalent source-tree form: `python -m sim <subcommand>` inside the repo,
or `python3 plugins/sim/scripts/sim_launcher.py <subcommand>` for the Docker
path. `run`/`respond` also accept `--only`/`--decision-ref` options; see the
CLI help (`python -m sim <subcommand> --help`) for details.
