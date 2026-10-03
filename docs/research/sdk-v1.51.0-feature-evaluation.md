# OpenHands SDK v1.51.0 feature evaluation (simulation-agent)

Scope: `openhands-sdk` and `openhands-tools` move from 1.50.1 to 1.51.0
(PyPI upload 2026-10-03). The complete upstream range `v1.50.1..v1.51.0`
(18 merge commits) was reviewed. uv moves 0.12.21 -> 0.12.22, and the
`OPENEMS_COMMIT` build pin advances to upstream `main`.

Primary source: [OpenHands SDK v1.51.0 release](https://github.com/OpenHands/software-agent-sdk/releases/tag/v1.51.0).

## SDK 1.50.1 -> 1.51.0

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| #5332 `prompt_cache_key` resolved via real provider for proxied models | adopted implicitly | Bug fix inside the LLM path; no plugin configuration references `prompt_cache_key`, so behavior improves with the pin only. |
| #5274 OpenRouter becomes a verified provider | available, not adopted | No VibeBB profile or plugin agent configures OpenRouter; the provider is simply usable now if a future profile selects it. |
| #4945, #5415 upstream CI fixes | not applicable | Upstream GitHub Actions internals; no repository surface consumes them. |
| #5434 `ACPAgentSettings.llm` deprecated | not applicable | The plugin does not run ACP agents; the deprecation needs no code change. |
| #5417 agent-server `/switch_llm` provider resolution | upstream image | simulation-agent ships only `sim-tools`/`sim-tools-em`; it does not build or pin an agent-server image, so this fix flows to whichever server image downstream deployments run. |
| #5412 direct-routing classifier messages (system+user) | adopted implicitly | Router-path bug fix; the plugin does not configure custom routing, so the corrected behavior arrives with the pin. |
| #5425, #5428 TypeScript client dependency bumps | not applicable | This repository does not use the SDK TypeScript client. |
| #5419 pydantic 2.12.5 -> 2.13.5 | lock-only | Picked up transitively through `uv.lock`; no direct pin change needed. |
| #1326 `find_dotenv` assertion fix in local conversation | adopted implicitly | Plugins run local conversations, so this crash fix is valuable; no code change needed. |
| #5151 agent-profiles: `tools` is the only tool control | already aligned | The deprecated `enable_sub_agents`/`enable_switch_llm_tool` switches (deprecated 1.51.0, removed 1.56.0) were never used here — every plugin agent already declares its `tools:` frontmatter list, including `task` sub-agents where needed. |
| #5449 profile persona replacement | not adopted | sim-analyst/sim-liaison/sim-review keep their own personas; no profile switches personas today. |
| #5450 tools supply system-prompt guidance (browser) | adopted implicitly | Internal refactor of how tool guidance is injected; consistent with the `tools:` frontmatter already in use. |
| #5397 stress-test run-slot fix | not applicable | Upstream test-only change. |
| #5358 delegated sub-agents stay within profile tools/MCP | adopted implicitly | Hardening for delegated `task` sub-agents; the plugin's tool scoping stays unchanged. |
| #5406 unified agent launch via resolve and finalize | adopted implicitly | Launch-path consolidation; no plugin-level change required. |

## uv 0.12.21 -> 0.12.22

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| CPython 3.10.22/3.11.17/3.12.15/3.13.16/3.14.8 builds | inherent | The tools image gains CPython 3.12.15 at the next publish build. |
| Workspace-member default groups / dependency-group Python requirements recorded in lockfiles | not applicable | simulation-agent is not a uv workspace; the recorded-group changes do not alter this repo's lockfile semantics. |
| `UV_PYTHON_ARCH` interpreter-architecture selector | not adopted | The image and workflows install a single architecture; no selector needed. |
| `--no-default-groups` honored in `uv audit`; clearer offline errors | not adopted | The repo does not run `uv audit` in CI today; weekly checks use `check_dependency_updates.py` instead. |
| Lockfile-hash verification on relock; frozen-sync workspace fixes; binary-size reduction; URL/path CLI formatting; `uv publish` help cleanup | inherent | Correctness and polish improvements carried by the new pin. |
| Rust MSRV 1.97 / toolchain 1.99 | not applicable | uv is consumed as a prebuilt binary. |

## openEMS pin 89c21b8 -> 81f32e0

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| Super-repo "update submodules": CSXCAD 0306a9f -> 65e7591, openEMS 174f52a -> 6761a36 | adopted via pin | Source build procedure unchanged; the pin itself is the integrity anchor (no paired checksum exists). |
| CSXCAD: accept numpy scalars as material property values | inherent | Python API tolerance improvement inside the solver; subprocess-only usage unaffected. |
| openEMS: DebyeMaterial pole-capacitor integration fix; per-order position-array free; flat-loss substrate example | inherent | Solver correctness/memory fixes plus an example; no repo-side adoption needed. |

## Compatibility deferrals

MCP 2.x remains deferred: openhands-sdk 1.51.0 still requires
`fastmcp>=3.2.0,<4`, which caps `mcp<2` (installed 1.30.0). The deferral in
`scripts/dependency_update_deferrals.json` was refreshed to `latest: 2.3.0`
with the 1.51.0 reason; `review_by` is unchanged.
