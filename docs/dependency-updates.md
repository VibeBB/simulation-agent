# Dependency update checks

Run `uv run python scripts/check_dependency_updates.py --markdown report.md`
to review direct and locked PyPI dependencies, the uv pin, GitHub Actions
and `uvx` pins, Docker ARGs and base tags, workflow `git clone --branch`
pins, and Python minor versions.

`BASE_IMAGE` is compared with the latest supported Ubuntu LTS tag. Its sha256
digest is also reported for manual review against the current Docker Hub tag.
The `OPENEMS_COMMIT` and `KICAD_RFSIM_COMMIT` Docker ARGs are compared with
their upstream default branch heads. The solver `NGSPICE_VERSION` and
`CALCULIX_CCX_VERSION` Docker ARGs are `docker-deb` targets compared with
the versions published in Debian unstable (sid) via `sources.debian.org` —
the Dockerfile fetches the sid `.debs` from a permanent snapshot.debian.org
archive URL and verifies them against the matching `*_DEB_SHA256` pins
(sid is never added to `sources.list`; their `Depends` resolve from
resolute). When the weekly report flags a newer sid upload, refresh the
version, the snapshot URL, and the sha256 together. Workflow `git clone --branch` pins
(currently the CISOfy/lynis checkout in `container-audit.yml`) are compared
with the upstream repo's highest semver tag. The `sim-tools-em` source build
is optional and remains separate from the published `sim-tools` image.

The scheduled workflow writes reports to the runner's temporary directory,
adds the run URL to the Markdown summary, and leaves the report issue open
while any dependency lookup is unknown.

Deferrals belong in `scripts/dependency_update_deferrals.json`. Each entry is
scoped to a surface, dependency, exact latest value, reason, and review date.
Remove or renew a deferral after review; expired deferrals do not suppress
update candidates.

## Update history


### 2026-10-29 — sdk 1.59.0, uv 0.13.6, openEMS/kicad-rfsim pins

Full changelog review: [SDK v1.59.0 feature evaluation](research/sdk-v1.59.0-feature-evaluation.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| openhands-sdk / openhands-tools | `==1.55.1` -> `==1.59.0` | Adopted; see research doc. |
| uv | `==0.13.1` -> `==0.13.6` | Adopted. |
| pytest / ruff | `9.1.1` -> `9.2.0`, `0.17.0` -> `0.17.3` (lock) | Adopted. |
| trivy | `v0.76.0` -> `v0.76.1` | Adopted. |
| codeql-action / harden-runner / setup-uv / login-action | v4.39.0->v4.39.1, v2.22.1->v2.22.3, v10.3.0->v10.3.3, v4.6.0->v4.7.0 | Adopted. |
| `OPENEMS_COMMIT` | `8370af8` -> `38da98d` | Adopted; build unchanged. |
| `KICAD_RFSIM_COMMIT` | `efa0ea9` -> `5143601` | Adopted; build unchanged. |
| emsdk base image | `6.0.12` -> `6.0.13` (digest re-pinned) | Adopted. |
| `ubuntu:26.04` base | digest re-pinned | Adopted. |
### 2026-10-18 — sdk 1.55.1, uv 0.13.1, openEMS pin

Full changelog review: [SDK v1.55.1 feature evaluation](research/sdk-v1.55.1-feature-evaluation.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| openhands-sdk / openhands-tools | `==1.54.0` -> `==1.55.1` | Adopted; see research doc. |
| uv | `==0.13.0` -> `==0.13.1` | Adopted. |
| zizmor | `1.30.1` -> `1.31.1` | Adopted. |
| trivy | `v0.75.0` -> `v0.76.0` | Adopted. |
| codeql-action | v4.38.3 -> v4.39.0 | Adopted. |
| `OPENEMS_COMMIT` | `974294b` -> `8370af8` | Adopted; build unchanged. |

### 2026-10-07 — solver sid .deb pins (ngspice 47, CalculiX 2.23)

Full changelog review: [Solver sid-.deb adoption (ngspice 47, CalculiX 2.23)](research/solver-sid-deb-adoption.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| ngspice | resolute apt `45.2+ds-1` -> sid `.deb` `47+ds-1` | Adopted. PSS update, small-signal noise for code models, `.sndprint`/`.sndparam`, VDMOS soft-recovery diode, adc/dac_bridge multi-bit, dc-sweep capacitance, `newcompat.ki`, TSTEP/TSTOP, `pyplot` reviewed; see research doc for adoption/non-adoption notes. |
| calculix-ccx | resolute apt `2.21-1build1` -> sid `.deb` `2.23-1` | Adopted. `*DAMAGE INITIATION`, submodel heat transfer, C3D8I correction, `*REFINE MESH,SMOOTHING ONLY`, composite-shell `*HEAT TRANSFER`, contact in `*CYCLIC SYMMETRY MODEL`, `*EQUATION` node-set first term reviewed; see research doc. |

### 2026-10-07 — sdk 1.54.0

Full changelog review: [SDK v1.54.0 feature evaluation](research/sdk-v1.54.0-feature-evaluation.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| `openhands-sdk` / `openhands-tools` (sdk-check group) | 1.52.0 -> 1.54.0 | Adopted. All 6 upstream PRs reviewed; skills-scan fix adopted implicitly, canvas-extension icon available but not adopted (no canvas extensions), release-CI/docs/test changes not applicable. |
| mcp | deferred at <2 | openhands-sdk 1.54.0 still requires `fastmcp<4` -> `mcp<2`; deferral reason refreshed to cite 1.54.0. |

### 2026-10-05 — sdk 1.52.0

Full changelog review: [SDK v1.52.0 feature evaluation](research/sdk-v1.52.0-feature-evaluation.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| `openhands-sdk` / `openhands-tools` (sdk-check group) | 1.51.0 -> 1.52.0 | Adopted. All 19 upstream commits reviewed; fixes adopted implicitly, agent-server/TS-client changes not applicable. |
| mcp | deferred at <2 | openhands-sdk 1.52.0 still requires `fastmcp<4` -> `mcp<2`; deferral reason refreshed to cite 1.52.0. |

### 2026-10-04 — GitHub Actions latest state, Python 3.14, 3.15 canary

| Component | From -> To | Decision |
| --- | --- | --- |
| uv | 0.12.22 -> 0.13.0 | Adopted. `required-version`, `ARG UV_VERSION`, `UV_DIGEST`, `sim.uv.version` OCI label, tests, README updated. |
| Python pins | 3.12 -> 3.14 | Adopted. Image `uv python install`/`python3.x` paths, `.python-version`, scalar workflow pins, and a new ci.yml matrix leg. |
| Python 3.15 | - -> canary leg | Adopted as experimental matrix leg (step-level `continue-on-error` + `::warning::` report). Deferred as default (now recorded for every `python-version` surface via a `*` deferral): `openhands-sdk` -> `litellm` -> `fastuuid==0.14.0` ships only an sdist whose bundled PyO3 fails to build on 3.15 (`uv sync` fails at maturin, verified 2026-10-12); `pydantic-core>=2.50` ships cp315 wheels, so fastuuid is the sole blocker. The leg detects when a 3.15-capable fastuuid lands. |

### 2026-10-03 — sdk 1.51.0, uv 0.12.22, openEMS pin

Full changelog review: [SDK v1.51.0 feature evaluation](research/sdk-v1.51.0-feature-evaluation.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| `openhands-sdk` / `openhands-tools` (sdk-check group) | 1.50.1 -> 1.51.0 | Adopted. All 18 upstream commits reviewed; fixes adopted implicitly, agent-profiles `tools:` contract already matches plugin frontmatter. |
| uv | 0.12.21 -> 0.12.22 | Adopted. `required-version`, `ARG UV_VERSION`, `UV_DIGEST` (multi-arch index digest), `sim.uv.version` OCI label, tests, README, AGENTS updated. |
| `OPENEMS_COMMIT` | 89c21b8 -> 81f32e0 | Adopted. One super-repo commit bumping CSXCAD (numpy-scalar material values) and openEMS (DebyeMaterial fix, memory free, example). Build unchanged. |
| `OPENEMS_COMMIT` | 81f32e0 -> 974294b | Adopted. Two super-repo commits: submodule refresh + `release: v0.37.0` tag. Build unchanged. |
| anchore/sbom-action | already v0.24.3 | No change; pinned at the v0.24.3 commit SHA already. |
| `KICAD_RFSIM_COMMIT` | already at HEAD | No change; pin equals upstream `main`. |
| ruff | already 0.16.10 | Already resolved at 0.16.10 in `uv.lock`; no new diagnostics. |
| `uv.lock` transitive drift | ~25 entries | All within existing specifiers (cyclopts 5.1.1, openapi-pydantic 0.6.0, pyjwt 2.15.1, litellm 1.103.2, etc.). |
| mcp | deferred at <2 | openhands-sdk 1.51.0 still requires `fastmcp<4` -> `mcp<2`; deferral refreshed to `latest: 2.3.0`. |
| Python 3.14 | deferred | Unchanged; SDK support unconfirmed. |

Publish-owned locks (`docker/image-digests.json`,
`plugins/sim/tools-image.json`) intentionally keep recorded image contents
until the next image publish — they are not hand-edited.
