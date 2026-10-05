# Development

## Setup

```bash
uv sync --locked          # uv 0.12.23, Python 3.12+, locked deps
```

Runtime deps are `pydantic>=2` and `mcp>=1.29,<2`; the `sdk-check` group
is needed for the plugin-load check.

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest                                   # full suite
env -u BASH_ENV -u "BASH_FUNC_gh%%" uv run pytest tests/<file>.py
uv run python scripts/verify_all.py --stage fast      # pytest + 77% cov gate
uv run python scripts/verify_all.py --stage standard
uv run python scripts/verify_docs.py
uv run python scripts/check_shared_hooks.py
uv run --group sdk-check python scripts/check_plugin_load.py
uvx zizmor .github/workflows
actionlint -oneline
```

The `env -u BASH_ENV -u "BASH_FUNC_gh%%"` prefix is required in shells
where a `gh` function is injected into the environment — it breaks the
stubbed-`gh` tests otherwise. `verify_all.py` supports `--group`,
`--match`, `--shard K/N`, and `--list`. Real-solver tests carry the
`tools` marker and skip only when ngspice/CalculiX are absent.

## CI

Required checks cover lint, unit (with the coverage gate), docker, docs,
and workflow lint. Shared hooks are canonical across 11 sister copies —
edit them together and update `EXPECTED` in
`scripts/check_shared_hooks.py`; the same applies to the 11 shared
workflows (`check_shared_workflows.py`). Steps that run only on `main` or
manual dispatch are listed in
[operations.md](operations.md) under "Main-only verification boundary".

## Release

`release.yml` (with a `dry_run` rehearsal input) drives
`scripts/release_bump.sh` for version arithmetic and tagging.
`publish-sim-images.yml` builds and publishes `sim-tools` (dry-run
supported), and digest-lock PRs are cut by
`scripts/publish_image_pin_pr.sh`. See [operations.md](operations.md)
for the full machinery.
