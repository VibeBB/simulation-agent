# ADR-0012: mruby/c Emscripten WASM leg

Status: Accepted
Date: 2026-10-12

## Context

firmware-agent gained a mruby/c runtime for embedded UX logic
(VibeBB/firmware-agent#125) and dashboard-agent gained the same
Emscripten leg (VibeBB/dashboard-agent#189). simulation-agent needs the
identical capability so a brief can run UX `.rb` sources in the mruby/c
WASM VM and assert the transcript — the same toolchain CI uses.

## Decision

- New brief section `mrubyc`: `sources` (workspace-relative `.rb` files),
  optional `memory_size` (default 64 KiB) and `expect` transcript
  substrings.
- `src/sim/mrubyc.py` mirrors the dashboard pipeline: `mrbc -B` compiles
  each source, a generated shim exports `mruby_ux_init`/`mruby_ux_run`,
  emcc links mruby/c core + upstream `hal/emscripten` (`-sASYNCIFY`), and
  Node runs every task to completion.
- Checks `mrubyc.tools` (missing emcc/node/mrbc/tree → `unknown`),
  `mrubyc.build` (compile/link errors → `fail`), `mrubyc.vm` (run →
  pass/fail on exit code + transcript detail), and one
  `mrubyc.transcript[<expect>]` per declared expectation.
- sim-tools image gains the pinned `emscripten/emsdk:6.0.10` stage plus a
  `mruby` build stage (mruby 4.0.0 → `mrbc`, mrubyc @ `2dec4802`, both
  sha256-verified) — identical pins to firmware-agent and
  dashboard-agent.

## Consequences

The image grows one build stage (ruby/build-essential/bison, sources
discarded) and three runtime payloads (`/opt/mruby/bin/mrbc`,
`/opt/mrubyc`, `/opt/emsdk`). Missing tools degrade to `unknown` per the
brief invariants rather than failing the gate.
