# ADR-0013: mruby/c device-API stubs for the Emscripten leg

Status: Accepted
Date: 2026-10-12

## Context

UX-creator-agent authors device APIs in `*.mruby-api.json` (class/method
surfaces for embedded hardware, per VibeBB/firmware-agent#127 and
VibeBB/UX-creator-agent#154) and firmware-agent generates the real C
bindings from the same file. A brief whose `mrubyc` section runs UX `.rb`
logic off-target fails the moment that logic calls a device class —
`LED.set` is not defined in a bare mruby/c VM.

## Decision

- New optional `MrubycSection.api_spec`: a workspace-relative
  `*.mruby-api.json` path.
- `src/sim/mruby_stub.py` renders `sim_api_stub.{c,h}` from the spec: the
  same class/module surface defined with `mrbc_define_class*` /
  `mrbc_define_module*` / `mrbc_define_class_under` /
  `mrbc_define_module_under` (topologically ordered so outer and super
  classes land first), class constants via `mrbc_set_class_const`,
  instance classes via `mrbc_instance_new` + zeroed `data[]` +
  `mrbc_define_destructor`, and every method as a C function that:
  - gates `access: "system_task"` on `vm->vm_id != system_task.vm_id`
    (returns `nil` for non-system tasks, mirroring firmware),
  - decodes positional args with the OpenBlink do-while(0) idiom —
    `argc < i` for a required slot `i` (argc excludes the receiver),
    `argc >= i` for optional slots, `MRBC_TT_*` type checks — raising
    `ArgumentError` on failure when `arg_errors: "raise"` and returning
    `nil` when `"silent"`,
  - decodes keywords with `MRBC_KW_ARG` + `MRBC_KW_MANDATORY` +
    `MRBC_KW_END` + `MRBC_KW_DELETE`, `MRBC_KW_DICT(rest)` for
    `rest_kwargs`, and trailing blocks at `v[argc + 1]` (or
    `v[argc + 2]` after a keyword hash),
  - writes a transcript line `API <Class>.<method>(<arg>=<value>...)` so
    `expect` entries assert device-API behavior, and
  - returns a deterministic neutral value of the declared type: `true`,
    `0`, `0.0`, the spec's first symbol, the method's qualified name for
    `string`, a `cap`-sized zero-filled array for `array<int>` /
    `array<float>`, or `nil`.
- `expert` methods register under `#if defined(<expert_define>)` exactly
  like firmware, so a debug flag flips the surface identically.
- New check `mrubyc.api` fails when the spec is missing or does not
  parse as `schema_version: 1` / `artifact_kind: "mruby_api"`; the stub
  schema ignores unknown fields so a newer UX schema still works with an
  older sim.
- The stub schema deliberately drops `handler` names — stubs never call
  firmware driver functions; the JSON is the contract, never shared
  code.

## Consequences

A brief can now assert that UX logic exercises the device API correctly
(`expect: ["API LED.set(part=led1, state=true)"]`) without hardware.
Stubs prove the *calling convention*, not device behavior — a `nil`
return from a system-task-gated method on the wrong VM is faithful to
firmware, but a stub never drives real hardware state.
