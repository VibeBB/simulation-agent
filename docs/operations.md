# Operations

## SBOM attestations

`publish-sim-images.yml` generates and attests a package-level SPDX-2.3 SBOM
for the published tools digest and uploads the full Syft SBOM as a 90-day
workflow-run artifact. The returned URL is stored as `sbom_attestation`;
`locked-image-check.yml` verifies it when present and
warns while continuing when it is absent.
The attested SBOM omits file entries and relationships involving files to
stay below the 16 MiB limit.

## Runtime configuration

The CLI workspace is `OPENHANDS_PROJECT_DIR`, falling back to the current
directory. Relative input and output paths must resolve within that workspace.
Paths that traverse symlinks are rejected.
The plugin launcher accepts `SIM_LAUNCH_MODE=docker|host|auto` (default
`docker`) and `SIM_TOOLS_IMAGE`. Docker mode requires Docker and a resolvable
image; if either is unavailable, set `SIM_LAUNCH_MODE=host` to run from the
resolved source tree. Host mode reports missing solver tools as `unknown`.
Auto mode retains Docker-when-available behavior and otherwise uses the host.

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

The `Publish sim images` workflow attests the published `sim-tools` image and
stores the attestation URL with its root and plugin digest locks.
`Locked image check` validates the lock and verifies available provenance
before pulling the image; legacy entries without attestation metadata warn
and continue. A verification failure fails the check. See
[ADR-0007](adr/ADR-0007-attest-published-tools-images.md).

## Docker images

`sim-tools` is based on Ubuntu 26.04.1 LTS (Resolute), pinned by the
`BASE_IMAGE` reference
`docker.io/library/ubuntu:26.04@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78`.
Both Docker stages use this same base. Resolute provides `calculix-ccx`
`2.21-1build1`, ngspice `45.2+ds-1`, and system Python
`3.14.3-0ubuntu2`; the simulation application itself remains in its
uv-managed Python `3.12.14` environment. Debian Trixie has no
`calculix-ccx` installation candidate; it only publishes
`calculix-ccx-test` `2.22-1`, which recommends the unavailable solver. This
is why the solver image uses Ubuntu. CI runners also use Ubuntu 26.04.

The openEMS build dependencies include CMake `4.2.3`, Boost `1.90`, VTK
`9.5.2`, HDF5 `1.14.6`, OpenMPI `5.0.10`, CGAL `6.1.1`, SWIG `4.4`,
Cython3 `3.1.6`, NumPy `2.3.5`, and h5py `3.15.1`. The Dockerfile installs
the corresponding `cmake`, `libboost-all-dev`, `libvtk9-dev`,
`libhdf5-dev`, `libopenmpi-dev`, `libcgal-dev`, `swig`, `cython3`,
`python3-numpy`, and `python3-h5py` packages, plus the TinyXML, FFTW,
readline, and XML development packages used by the source build.

The final-stage runtime package list was derived from `ldd` on
`/usr/local/bin/openEMS`, the installed openEMS/CSXCAD libraries, and their
Python extension modules. The native dependencies include Boost
program-options/thread `1.90.0-6ubuntu1`, HDF5 `1.14.6+repack-2`, TinyXML
`2.6.2-7build1`, and VTK `9.5.2+dfsg4-3ubuntu1`, packaged as
`libboost-program-options1.90.0`, `libboost-thread1.90.0`, `libhdf5-310`,
`libtinyxml2.6.2v5`, and `libvtk9.5`. The checked libraries and extensions
had no unresolved `ldd` entries. No `libxml2` dependency appeared, so no
libxml2 runtime package is installed. APT package revisions are resolved
from Ubuntu repositories during image builds; the base digest is pinned but
APT resolution is not a byte-for-byte lock.

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
They are built with system Python `/usr/bin/python3` `3.14.3`,
Cython3 `3.1.6+dfsg-1ubuntu2`, NumPy `1:2.3.5+ds-3ubuntu1`, and h5py
`3.15.1-4build1`. The tested bindings report CSXCAD `0.7.0` and openEMS
`0.37.0`; the application itself uses its locked uv environment.

Build and smoke-test locally:

```bash
docker buildx build --load --target sim-tools -f docker/sim-tools.Dockerfile -t sim-tools:local .
uv run python scripts/smoke_image.py --image sim-tools:local
docker buildx build --load --target sim-tools-em -f docker/sim-tools.Dockerfile -t sim-tools-em:local .
```

The base-image smoke check leaves its named containers stopped for inspection
and reuse.

The optional openEMS build is intentionally attempted only after the base
image passes. If it exceeds 60 minutes or fails for a non-trivial reason, stop
and report the exact error rather than applying an unreviewed workaround.

## User images and vision

The `intake-attachments` hook scans conversation events at session start,
before each user prompt, and when the session stops. User-attached images are
materialized under `intake/attachments/`; `manifest.jsonl` records their
source event, image digest, and materialization status. If the event store is
not available to the runtime, users can place images in that directory
directly and provide their paths.

`ensure-llm-profiles` provisions missing `vibebb-author` and `vibebb-review`
profiles from the active profile without overwriting existing profiles. Its
vision status is advisory: disabled or unsupported models are distinguished
from profiles the optional SDK probe cannot verify.

Post-tool hooks append image views and successful `inspect_image_with_vision`
responses to `observations/sim/image-observations.jsonl` and
`observations/sim/vision-tool-events.jsonl`. The logs and attachment manifest
are generated evidence and cannot be edited directly. Image observations are
L2 advisory data only; they never supply measured values or change a
deterministic verdict. See [ADR-0004](adr/0004-vision-and-profile-hooks.md).

## Outputs and evidence

Reports are generated in `out/<name>/`; never edit them directly. `manifest.json`
hashes generated files, and `provenance.json` records the brief hash, import
hashes, tool versions, and a UTC timestamp. Keep authored inputs and generated
outputs distinct.

## Launcher-side verification

`SIM_VERIFY_ATTESTATION` accepts `auto` (the default), `require`, or `off`.
Before pulling a lock-provided image, and on every `prewarm`, the launcher
uses `gh attestation verify` with the lock entry and publisher workflow.
`auto` prints one note and skips for an image override, missing attestation,
missing `gh`, or failed `gh auth status`; once verification starts, failure
or timeout prevents the pull. `require` makes skip conditions errors, while
`off` never verifies. Ordinary invocations do not re-verify a locally
present image, and `--warn` doctor paths never verify.

## Container hardening

Three layers were adopted after a comparative evaluation of Lynis,
`docker build --check`, Trivy, Grype, Dockle, and hadolint:

- **Dockerfile lint** (`dockerfile-lint` job in `ci.yml`): hadolint
  v2.15.1 via `hadolint-action` v3.5.0 plus `docker build --check`
  (BuildKit built-in). `.hadolint.yaml` allows only docker.io and
  ghcr.io registries and waives DL3008 (exact deb pins rot when archives
  drop them; downloaded tools are already version+sha256/commit pinned)
  and DL3066 (the `sim` account is intentionally named, system uid
  10001).
- **Image scan on publish** (`publish-sim-images.yml`): Trivy v0.75.0
  via `trivy-action` v0.36.0 scans the pushed `sim-tools` digest for
  CRITICAL/HIGH fixable vulnerabilities, secrets, and misconfiguration,
  gated (`exit-code 1`), with SARIF uploaded to code scanning
  (`category: trivy-sim-tools`) and a full JSON report as an artifact.
  The action is SHA-pinned and `version:` is explicit — the March 2026
  Trivy supply-chain compromise made both non-negotiable.
- **Weekly audit** (`container-audit.yml`, Mondays 03:37 UTC): pulls the
  pinned digests from `docker/image-digests.json`, re-scans every
  published image with a fresh vulnerability DB (new CVEs against frozen
  images), runs the Docker CIS compliance report and an informational
  in-image Lynis 3.1.7 audit on the primary `sim-tools` image,
  aggregates `container-hardening.json` (artifact), and edits/creates a
  "Container hardening report" issue. The issue closes automatically
  when fixable HIGH/CRITICAL findings reach zero. The Lynis Hardening
  Index is recorded as a trend metric only — its denominator shifts
  with container-skipped tests, so it never gates.

Not adopted, with reasons: `lynis audit dockerfile` (~6 greps, frozen
since 2018, subset of hadolint, hardening index always 1);
Dockle (v0.4.15 stale; its CIS-derived checks are covered by Trivy's
`--compliance docker-cis` report); Grype (equivalent for the SBOM path,
kept as fallback); checkov (redundant third linter); `cisofy/lynis`
Docker image (does not exist — Lynis runs from a pinned git clone);
non-root USER enforcement and HEALTHCHECK enforcement (CI tools images —
deferred policy decisions).

First gate outcome: the publish Trivy scan flagged four fixable HIGHs in
the uv-managed CPython's bundled `pip` payload (`pip/_vendor` urllib3
2.7.0, msgpack 1.1.2, setuptools 70.3.0) plus the `ensurepip` bundle.
Nothing in the image invokes pip — dependencies install via `uv` at
build time and the entrypoint venv is pip-less — so `sim-tools`
strips `bin/pip*`, `site-packages/pip*`, and `ensurepip` from the
managed interpreter in the same layer that installs it (deterministic;
no new pins). `uv pip` still works against the interpreter if ever
needed. This was preferred over `.trivyignore` waivers because a real
fix exists.

Changelog evaluation for the adopted pins is in the introducing PR.
Suppressions: `.hadolint.yaml` waivers above; `.trivyignore` holds
time-boxed finding IDs — entries must carry an `exp:` date and a
rationale line here when added.

The weekly audit runs Lynis with the committed
`docker/lynis-container.prf` profile, which skips tests that are
inapplicable inside a container (kernel/systemd/mounts/storage/
network/PAM/accounting are governed by the runtime flags below, not the
image filesystem), so the Hardening Index and suggestion list reflect
image-controlled state. Remaining suggestions are fixed in the
Dockerfile (`UMASK 027` in login.defs, inherited by `sim-tools-em`) or
silenced only with a documented reason.

`sim_launcher.py` applies the runtime-hardening flags the container
profile defers to: `--network none`, `--user uid:gid`,
`--cap-drop ALL`, `--security-opt no-new-privileges`. A `--read-only`
root filesystem stays an optional hardening for callers that supply
tmpfs for tools that need scratch space.

## CI runner network auditing

Every job in every workflow uses `step-security/harden-runner` in audit-only mode. It observes network egress without blocking requests; per-run insights are available in the GitHub Actions job summary.

## SDK 1.51.0 feature evaluation

See [simulation-agent SDK v1.51.0 feature evaluation](research/sdk-v1.51.0-feature-evaluation.md).

## Digest-lock PR verification

The publisher dispatches `ci.yml` and `workflow-lint.yml` on the lock branch, then polls the authoritative required-check set for up to 30 minutes. Non-required failures do not block publishing; a concluded required-check failure or a PR closed without merge fails the job. A PR merged externally triggers the existing post-merge main workflows without waiting for their results. If required checks remain pending at the deadline, the publisher arms squash auto-merge with branch deletion and exits successfully so branch protection can complete the merge.

SPDX generation prefers the GHCR registry source, writes temporary data under
the runner's temporary directory, and disables file metadata. The publisher
removes file entries and relationships involving files to produce the
package-level SPDX-2.3 SBOM. A guard reports disk space and the attested SBOM
size after transformation and fails above 16 MiB; the full Syft SBOM is
uploaded as a 90-day workflow-run artifact.

## Settings-level posture (recorded decisions)

The following live in repository Settings rather than code; they are
intentional for the solo-maintainer bot-merge workflow and are recorded here
so audits do not re-flag them:

- Branch protection does not require approving reviews, code owners, or
  "apply to administrators": every merge is performed by automation
  (digest-lock, version-bump, and Devin PRs), so required approvers would
  only add friction to a pipeline that already gates on the required-check
  set. OpenSSF Scorecard reports this as Branch-Protection 3 and
  Code-Review 0; that is the recorded trade-off, not an oversight.
- The Dependency graph must stay enabled for `dependency-review.yml` to
  evaluate pull requests.
- `release.yml` is dispatch-only; run it once with `dry_run=true` before the
  first real release to rehearse bump, verify, and install-smoke without
  creating a GitHub release.
