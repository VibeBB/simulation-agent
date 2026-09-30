# OpenHands SDK v1.50.0 feature evaluation (simulation-agent)

Scope: openhands-sdk / openhands-tools 1.49.6 -> 1.50.0 (PyPI upload
2026-09-29), uv 0.12.19 -> 0.12.21, and the Agent Canvas state at the time
of the bump. Every commit in `v1.49.6..v1.50.0` of
OpenHands/software-agent-sdk (25 commits) and both uv releases (0.12.20,
0.12.21) were reviewed. Decisions: **adopted** (repo change in this PR),
**inherent** (arrives with the pin, no repo change), **n/a** (does not
touch this plugin), **deferred** (useful, blocked; revisit trigger given).

## SDK 1.49.6 -> 1.50.0

| Upstream change | Decision | Notes for simulation-agent |
| --- | --- | --- |
| #5345 keep conversations alive when MCP startup fails | inherent | A missing tools image / Docker now degrades to "plugin MCP tools absent" instead of killing the conversation. The doctor hook already reports the cause; agents must not improvise results when `sim_*` tools are missing. |
| #5309 surface LiteLLM budget denials without retry backoff | inherent | Sub-agent `max_budget_per_run` caps and proxy budget denials now end the run immediately instead of retrying. |
| #5222 refresh-on-401 hook on managed-proxy LLMs (agent-server) | inherent | No agent-server image is built by this repo. |
| #5270 manage optional backend processes for Canvas apps (agent-server) | n/a | The plugin ships no Canvas extension/app backend. |
| #5013 client-owned browser event stream transport | n/a | TypeScript client only. |
| #5361 anyio 4.14.2 (CVE-2026-63374) | inherent | Picked up by the lock refresh. |
| #4967 resolve async response secrets outside the event loop | inherent | |
| #4159 centralize LLM call context | n/a | Internal refactor. |
| #5327 tolerate null `cache_creation_tokens` | inherent | |
| #5238 goal judge prompt split into system + user | n/a | Goal mode is not used. |
| #5143, #5148, #5149, #5241, #5242 condenser keeps the leading system prompt / splits summarization prompt | inherent | Long sub-agent runs keep the agent definition (and its fail-closed rules) after condensation or a hard context reset. |
| #5239 system message prepended to profile pre-flight ping | inherent | `vibebb-*` profile checks behave with system-first providers. |
| #5240 GraySwan analyzer system-first guarantee | n/a | Security analyzer not configured by the plugin. |
| #4322 anyOf `false` branch no longer widened to accept-all | n/a | MCP input schemas here are hand-written JSON without `anyOf`. |
| #4656 docstrings for image helper functions | inherent (informs vision design) | Confirms: for a non-vision model the SDK rewrites only images in the latest user message into `inspect_image_with_vision` references; images in tool observations are not delegated. |
| #5328 gate `prompt_cache_key` on provider support | inherent | |
| #5298 aiosqlite 0.22.1 | inherent | |
| #5286 OpenAPI exemption for tool metadata | n/a | |
| #5040, #5313, #4298, #5331, #5374 docs / CI / release | n/a | |

## uv 0.12.19 -> 0.12.21

| Release | Change | Decision |
| --- | --- | --- |
| 0.12.20 | Lockfile reuse when declarations are semantically equivalent; `--require-hashes` applies to repeated requirements; `uv upgrade` restores `pyproject.toml` on failure; XDG_CONFIG_DIRS fix; several panic fixes | inherent |
| 0.12.20 | Preview: lockfile-normalization, pylock.toml group/path fixes, tool-install-locks dedupe | n/a (preview features not enabled) |
| 0.12.21 | CPython builds use OpenSSL 3.5.9; empty `[manifest]` tables omitted from lockfiles; post-release/pre-release compatibility fix; `uv python pin --rm` global-file fix | inherent |
| 0.12.21 | Preview: `resolution-inputs` | n/a |

## Agent Canvas and community state

| Item | Decision |
| --- | --- |
| Agent Canvas v1.24.0 (2026-09-25) is still the latest release; it was evaluated with the v1.49.6 bump. | no change |
| OpenHands/OpenHands#17822 (open PR): inline previews for created SVG / PNG / PDF / Office artifacts in the chat. | deferred until released; rendered artifacts written with `file_editor create` would then preview inline for humans. |
| software-agent-sdk#5360 / #5367 (open): DeepSeek models have images stripped by `force_string_serializer`. | deferred; do not route `vibebb-review` to a DeepSeek vision model until #5367 ships. |
| software-agent-sdk#5351 (open): `VisionInspectTool` auto-attaches even with `include_default_tools=[]`. | n/a; plugin agents do not rely on disabling default tools. |
| software-agent-sdk#5381 (closed, not planned): a sub-agent's own `mcp_config` is not narrowed to the parent's tools. | noted; sub-agent `mcp_config` here only launches this plugin's own fail-closed server. |
| MCP 2.x / fastmcp 4.x: SDK 1.50.0 still requires `fastmcp>=3.2.0,<4` (and therefore `mcp<2`). | deferred (see `scripts/dependency_update_deferrals.json`). |

## Vision path after this bump

The effective vision route for plugin sub-agents is the `vibebb-review`
(and `vibebb-author`) profile itself: when that profile's model is
vision-capable, `file_editor view` on a PNG/JPEG and MCP `ImageContent`
tool results reach the model directly. `inspect_image_with_vision` only
covers images attached to the latest user message (the user's own
uploads in the main conversation), so it is not a fallback for rendered
workspace files.

## Verification

- `uv sync --locked --all-groups`, Ruff check and format, Pyright, `pytest -q`, `scripts/verify_all.py --stage fast`, plugin-load check, and docs verifier passed; 88 tests passed (two collection warnings).
- No `scripts/check_dependency_updates.py` exists in this repo.
- `uv.lock` resolves AnyIO 4.15.1 (at least 4.14.2).
- The default `sim-tools` build initially hit Docker Hub's unauthenticated 429 rate limit. Retrying with the same pinned Ubuntu digest through `mirror.gcr.io` built `sim-tools:dev`; `uv run python scripts/smoke_image.py --image sim-tools:dev` passed.
- Verification log: `/home/ubuntu/work/verify/simulation-agent-deps.log`.
