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

### 2026-10-07 — solver sid .deb pins (ngspice 47, CalculiX 2.23)

Full changelog review: [Solver sid-.deb adoption (ngspice 47, CalculiX 2.23)](research/solver-sid-deb-adoption.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| ngspice | resolute apt `45.2+ds-1` -> sid `.deb` `47+ds-1` | Adopted. PSS update, small-signal noise for code models, `.sndprint`/`.sndparam`, VDMOS soft-recovery diode, adc/dac_bridge multi-bit, dc-sweep capacitance, `newcompat.ki`, TSTEP/TSTOP, `pyplot` reviewed; see research doc for adoption/non-adoption notes. |
| calculix-ccx | resolute apt `2.21-1build1` -> sid `.deb` `2.23-1` | Adopted. `*DAMAGE INITIATION`, submodel heat transfer, C3D8I correction, `*REFINE MESH,SMOOTHING ONLY`, composite-shell `*HEAT TRANSFER`, contact in `*CYCLIC SYMMETRY MODEL`, `*EQUATION` node-set first term reviewed; see research doc. |

### 2026-10-07 — sdk 1.53.0

Full changelog review: [SDK v1.53.0 feature evaluation](research/sdk-v1.53.0-feature-evaluation.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| `openhands-sdk` / `openhands-tools` (sdk-check group) | 1.52.0 -> 1.53.0 | Adopted. All 6 upstream PRs reviewed; skills-scan fix adopted implicitly, canvas-extension icon available but not adopted (no canvas extensions), release-CI/docs/test changes not applicable. |
| mcp | deferred at <2 | openhands-sdk 1.53.0 still requires `fastmcp<4` -> `mcp<2`; deferral reason refreshed to cite 1.53.0. |

### 2026-10-05 — sdk 1.52.0

Full changelog review: [SDK v1.52.0 feature evaluation](research/sdk-v1.52.0-feature-evaluation.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| `openhands-sdk` / `openhands-tools` (sdk-check group) | 1.51.0 -> 1.52.0 | Adopted. All 19 upstream commits reviewed; fixes adopted implicitly, agent-server/TS-client changes not applicable. |
| mcp | deferred at <2 | openhands-sdk 1.52.0 still requires `fastmcp<4` -> `mcp<2`; deferral reason refreshed to cite 1.52.0. |

### 2026-10-04 — GitHub Actions latest state, Python 3.14, 3.15 canary

| Component | From -> To | Decision |
| --- | --- | --- |
| uv | 0.12.22 -> 0.12.23 | Adopted. `required-version`, `ARG UV_VERSION`, `UV_DIGEST`, `sim.uv.version` OCI label, tests, README updated. |
| Python pins | 3.12 -> 3.14 | Adopted. Image `uv python install`/`python3.x` paths, `.python-version`, scalar workflow pins, and a new ci.yml matrix leg. |
| Python 3.15 | - -> canary leg | Adopted as experimental matrix leg (step-level `continue-on-error` + `::warning::` report). Deferred as default: `openhands-sdk` -> `fastuuid==0.14.0` -> PyO3 0.26 caps interpreters at 3.14; the leg detects when upstream wheels land. |

### 2026-10-03 — sdk 1.51.0, uv 0.12.22, openEMS pin

Full changelog review: [SDK v1.51.0 feature evaluation](research/sdk-v1.51.0-feature-evaluation.md).

| Component | From -> To | Decision |
| --- | --- | --- |
| `openhands-sdk` / `openhands-tools` (sdk-check group) | 1.50.1 -> 1.51.0 | Adopted. All 18 upstream commits reviewed; fixes adopted implicitly, agent-profiles `tools:` contract already matches plugin frontmatter. |
| uv | 0.12.21 -> 0.12.22 | Adopted. `required-version`, `ARG UV_VERSION`, `UV_DIGEST` (multi-arch index digest), `sim.uv.version` OCI label, tests, README, AGENTS updated. |
| `OPENEMS_COMMIT` | 89c21b8 -> 81f32e0 | Adopted. One super-repo commit bumping CSXCAD (numpy-scalar material values) and openEMS (DebyeMaterial fix, memory free, example). Build unchanged. |
| anchore/sbom-action | already v0.24.3 | No change; pinned at the v0.24.3 commit SHA already. |
| `KICAD_RFSIM_COMMIT` | already at HEAD | No change; pin equals upstream `main`. |
| ruff | already 0.16.10 | Already resolved at 0.16.10 in `uv.lock`; no new diagnostics. |
| `uv.lock` transitive drift | ~25 entries | All within existing specifiers (cyclopts 5.1.1, openapi-pydantic 0.6.0, pyjwt 2.15.1, litellm 1.103.2, etc.). |
| mcp | deferred at <2 | openhands-sdk 1.51.0 still requires `fastmcp<4` -> `mcp<2`; deferral refreshed to `latest: 2.3.0`. |
| Python 3.14 | deferred | Unchanged; SDK support unconfirmed. |

Publish-owned locks (`docker/image-digests.json`,
`plugins/sim/tools-image.json`) intentionally keep recorded image contents
until the next image publish — they are not hand-edited.
