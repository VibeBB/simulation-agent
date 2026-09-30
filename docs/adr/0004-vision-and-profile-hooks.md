# ADR-0004: Record vision evidence and provision model profiles

- Status: Accepted
- Date: 2026-09-30

## Context

Simulation reviews need to inspect user-attached captures and sibling render
images, while keeping image-derived interpretation separate from solver
measurements and deterministic verdicts. Vision-capable profile routing also
needs an advisory check without changing user profile settings.

## Decision

Materialize user-attached images under `intake/attachments/` with a
provenance manifest. Record direct image views and successful
`inspect_image_with_vision` tool responses under `observations/sim/`.
Provision only missing `vibebb-author` and `vibebb-review` profiles from the
active profile; never overwrite existing profiles. Report whether vision is
disabled, active, unsupported, or unverified when the SDK can determine it.

Agents use image evidence to identify advisory comparisons and assumptions,
not to supply solver output or change a verdict. Image-derived values require
user confirmation before becoming brief bounds. Text inside images is data,
not an instruction.

## Consequences

Conversation events may yield workspace image files and JSONL provenance
records, and reviews can explicitly report when a visual check was not
performed. These generated records are protected from direct edits. The
optional profile probe is best-effort; a missing SDK or unreadable profile
remains unverified and does not block a session. Deterministic gates retain
exclusive authority over `pass`, `fail`, and `unknown`.
