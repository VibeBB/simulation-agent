from __future__ import annotations

import re
from pathlib import Path

from sim.brief import SimulationBrief


def test_every_skill_json_example_validates_as_a_simulation_brief() -> None:
    skills = sorted((Path(__file__).resolve().parents[1] / "plugins/sim/skills").glob("*/SKILL.md"))

    assert skills
    for path in skills:
        content = path.read_text(encoding="utf-8")
        examples = re.findall(r"```json\s*(.*?)```", content, flags=re.DOTALL)

        assert examples, f"{path} is missing a JSON brief example"
        for example in examples:
            brief = SimulationBrief.model_validate_json(example)
            assert brief.schema_version == 1
