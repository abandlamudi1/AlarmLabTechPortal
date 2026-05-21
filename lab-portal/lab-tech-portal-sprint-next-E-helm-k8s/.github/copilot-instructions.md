# GitHub Copilot Instructions — Lab Tech Portal

> **Canonical agent instructions are in [AGENTS.md](../AGENTS.md)** — read that file first.
> This file exists so GitHub Copilot's tool-discovery can find it; the substance lives in AGENTS.md.

## Quick orientation for Copilot

Before suggesting code changes, read the 2–3 most recent files in `changelogs/` and summarize key decisions and open items. Then consult [AGENTS.md](../AGENTS.md) for the full rule set.

Key reminders (full detail in AGENTS.md):
- PR titles: `QENG-16846: type(scope): summary` (umbrella epic prefix is mandatory)
- Infrastructure PRs require a **5-tool coverage matrix** — Inventory / RF Chamber / Checkout / System Locator / Print Requests
- Slice labels required on every issue: `slice-0-baseline`, `slice-a-auth`, `slice-b-observability`, `slice-c-resilience`, `slice-c2-scheduled`, `slice-d-part1`, `slice-d-part2`, `slice-g-part1`, `slice-g-part2`, `slice-h-closure`
- Run `python -m pytest` before declaring work complete
- Never hardcode credentials; use `.env` + tool-prefix convention (see [.env.example](../.env.example))
- Branch naming: `feature/sprint-N-<concern>` for sprint work, `feature/issue-NNN-<desc>` for isolated issues
