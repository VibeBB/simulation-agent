## SBOM attestations

The publisher generates an SPDX-2.3 SBOM for the digest-pinned tools image,
attests it with predicate type `https://spdx.dev/Document/v2.3`, and uploads
the artifact for 30 days. The returned URL is recorded as
`sbom_attestation`; locked-image checks verify it when present and warn when
absent. Unpinned locks cannot carry this metadata.
# ADR-0007: Attest published tools images

Status: Accepted

## Context

The `sim-tools` image is published to GHCR and consumed by digest from the
root image lock and the plugin's mirrored image pin. A digest identifies
image content but does not by itself record which workflow built and
published it.

## Decision

The publish workflow creates a GitHub Artifact Attestation for the tools
image digest and stores the returned attestation URL in both image-lock
entries. The locked-image check verifies pinned images with the repository's
publish workflow as the signer. Existing pins without attestation metadata
emit a warning and continue; a failed verification fails the check.

## Consequences

Published image provenance can be checked before running the locked image.
The publish job needs the `id-token: write` and `attestations: write`
permissions, and the verification job needs `attestations: read`.

## Launcher-side verification

`SIM_VERIFY_ATTESTATION` accepts `auto` (the default), `require`, or `off`.
Before pulling a lock-provided image, and on every `prewarm`, the launcher
uses `gh attestation verify` with the lock entry and publisher workflow.
`auto` prints one note and skips for an image override, missing attestation,
missing `gh`, or failed `gh auth status`; once verification starts, failure
or timeout prevents the pull. `require` makes skip conditions errors, while
`off` never verifies. Ordinary invocations do not re-verify a locally
present image, and `--warn` doctor paths never verify.
