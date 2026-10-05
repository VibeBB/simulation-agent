# Records and vision (VRP v1 for sim)

The VibeBB Record Protocol keeps an append-only, hash-verified trail of
what the agent decided, saw, and concluded under `observations/sim/`
(three logs: `decisions.jsonl`, `impressions.jsonl`,
`vision-reviews.jsonl`). The `require-records` hook is the enforcement
point: at `stop` it refuses a clean session when owed records are missing,
malformed, or tampered with.

## Stages

Stage slugs follow the workflow: `intake`, `brief`, `imports`, `analysis`,
`review`, `liaison`, `revision`.

## What gets recorded

- **Decisions** (`sim_record_decision` / `record decision`): every
  consequential choice — solver/method picks, limit interpretations,
  analysis inclusion or exclusion — with ≥2 considered options, first
  principles cited, a ≥200-char rationale, evidence refs (path+sha256 or
  named reference), assumptions, unknowns, residual risks, and a
  `revisit_when` trigger.
- **Stage impressions** (`sim_record_impression`): a long-form close-out
  per stage — ≥400 characters and ≥3 sentences describing what happened,
  what is worrying, and what comes next, bound to artifact hashes.
- **Vision reviews** (`sim_record_vision_review`): every image the agent
  looks at — each plot PNG, each intake attachment, each sister render.
  Findings carry category/severity/note; the impression follows the same
  400-char/3-sentence rule. Bound by `image_path`+`image_sha256` or by
  `source_event_id` of a recorded image observation.

## Vision points

Each generated plot has a checklist slug (see the `sim-vision-review`
skill): `sim-summary`, `margin-chart`, `spice-waveform`, `rf-sparams`,
`dft-testpoints`, `fem-deflection`, plus `intake-image` and
`sibling-render` for non-sim images. Findings are advisory — they never
change a gate verdict.

## Enforcement

- Every line appended through `records.py` is fully validated first; the
  `event_id` is sha256 over `{kind, sequence, body}`.
- `valid_event_ids` re-validates every log line and recomputes the hash —
  parity with the Stop-hook mirror (`_records.record_errors`) — and is
  what `ux_respond` and `write_response` consult when checking
  `decision_refs`/`impression_refs`. A forged or mutated line is refused.
- `protect-generated` denies edits to `observations/sim/*`, `out/`, and
  generated response files; fix inputs and regenerate.
