# Dependency update checks

Run `uv run python scripts/check_dependency_updates.py --markdown report.md`
to review direct and locked PyPI dependencies, the uv pin, GitHub Actions
and `uvx` pins, Docker ARGs and base tags, and Python minor versions.

`BASE_IMAGE` is compared with the latest supported Ubuntu LTS tag. Its sha256
digest is also reported for manual review against the current Docker Hub tag.
The `OPENEMS_COMMIT` and `KICAD_RFSIM_COMMIT` Docker ARGs are compared with
their upstream default branch heads. The `sim-tools-em` source build is
optional and remains separate from the published `sim-tools` image.

The scheduled workflow writes reports to the runner's temporary directory,
adds the run URL to the Markdown summary, and leaves the report issue open
while any dependency lookup is unknown.

Deferrals belong in `scripts/dependency_update_deferrals.json`. Each entry is
scoped to a surface, dependency, exact latest value, reason, and review date.
Remove or renew a deferral after review; expired deferrals do not suppress
update candidates.
