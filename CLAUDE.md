# CLAUDE.md

Claude Code reads this file. The project rules live in `AGENTS.md` so every agent (Claude Code, Cursor, others)
follows one copy; do not duplicate them here.

@AGENTS.md

## Claude Code specifics

- MCP servers are in `.mcp.json` (same two as `.cursor/mcp.json`; keep them in sync). Claude Code asks you to
  approve project servers on first launch. Keys come only from the environment (`.env`, never committed).
- Chemistry runs in Docker images `activesite-engine:at26` and `activesite-prep:at26` (build steps in README).
- Tests: `uv run pytest -q`.
