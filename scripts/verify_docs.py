from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def verify() -> list[str]:
    failures: list[str] = []
    required = (
        "README.md",
        "AGENTS.md",
        "CHANGELOG.md",
        "THIRD_PARTY.md",
        "docs/README.md",
        "docs/architecture.md",
        "docs/workflow.md",
        "docs/agents.md",
        "docs/skills.md",
        "docs/commands.md",
        "docs/mcp.md",
        "docs/hooks.md",
        "docs/contracts.md",
        "docs/records-and-vision.md",
        "docs/sister-cooperation.md",
        "docs/performance-and-limits.md",
        "docs/operations.md",
        "docs/development.md",
        "docs/improvement-notes.md",
        "docs/adr/0001-subprocess-only-solvers.md",
        "docs/adr/0002-sibling-contracts.md",
        "docs/adr/0003-verdict-semantics.md",
        "docs/adr/0009-records-liaison-vision.md",
        "docker/README.md",
    )
    for item in required:
        if not (ROOT / item).is_file():
            failures.append(f"missing required documentation: {item}")
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts or ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for link in LINK_RE.findall(text):
            target = link.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).resolve().exists():
                failures.append(f"{path.relative_to(ROOT)}: broken link {link}")
    plugin = ROOT / "plugins" / "sim"
    counts = {
        "agents": len(list((plugin / "agents").glob("*.md"))),
        "commands": len(list((plugin / "commands").glob("*.md"))),
        "skills": len(list((plugin / "skills").glob("*/SKILL.md"))),
    }
    expected = {"agents": 3, "commands": 17, "skills": 11}
    if counts != expected:
        failures.append(f"plugin inventory {counts!r} != {expected!r}")
    for path in sorted((plugin / "skills").glob("*/SKILL.md")):
        if "*.sim.json" not in path.read_text(encoding="utf-8") and path.parent.name in {
            "sim-brief",
            "sim-workflow",
        }:
            failures.append(f"{path.relative_to(ROOT)} does not mention *.sim.json")
    if "simulation.json" in (plugin / "skills" / "sim-workflow" / "SKILL.md").read_text(
        encoding="utf-8"
    ):
        failures.append("sim-workflow contains an obsolete brief suffix")
    return failures


def main() -> int:
    failures = verify()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("documentation and plugin inventory verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
