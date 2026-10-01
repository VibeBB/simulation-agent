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
