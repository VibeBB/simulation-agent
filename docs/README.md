# simulation-agent documentation

Technical documentation for the `sim` plugin. All content is derived from the
code base; when docs and code disagree, the code is right — please fix the doc
or file an issue.

## Contents

- [architecture.md](architecture.md) — layers, module map of `src/sim`, data flow
- [workflow.md](workflow.md) — the intake→brief→imports→analysis→review→liaison→revision stages
- [agents.md](agents.md) — the three agents, their tools, hooks, and budgets
- [skills.md](skills.md) — every skill and when it applies
- [commands.md](commands.md) — every `/sim:*` command
- [mcp.md](mcp.md) — every MCP tool: inputs, outputs, inline images, errors
- [hooks.md](hooks.md) — every hook by event: matcher, effect, exit codes
- [contracts.md](contracts.md) — every JSON contract: brief, imports, requests,
  responses, reports, liaison, VRP records
- [records-and-vision.md](records-and-vision.md) — VRP v1 for sim and the
  vision-review protocol
- [sister-cooperation.md](sister-cooperation.md) — SLP v2 and v1 request flows
  with the sister plugins
- [performance-and-limits.md](performance-and-limits.md) — solver timeouts,
  sampling limits, and known boundaries
- [operations.md](operations.md) — runtime environment, images, CI boundary
- [development.md](development.md) — dev setup, verification, release
- [test-coverage.md](test-coverage.md) — C0/C1/C2/MCC/MC/DC and boundary coverage, floors, test-design techniques
- [improvement-notes.md](improvement-notes.md) — running improvement list
- [adr/](adr/) — design decisions
- [research/](research/) — solver selection research (historical, unchanged)
