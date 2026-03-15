# AGENTS.md — AI Agent Context

This file helps AI coding agents (Claude Code, Copilot, Cursor, etc.) understand and work with this codebase effectively.

## Project summary

Mobius is an adversarial agent swarm orchestrator. It runs AI agents in parallel competitions, judges their outputs with a multi-provider panel, and uses Elo ratings to drive self-improvement.

## Entry points

- **CLI**: `src/mobius/cli.py` — all user commands via Typer
- **Orchestrator**: `src/mobius/orchestrator.py` — main competition flow
- **Experiments**: `experiments/run_experiment.py` — multi-round batch runner

## Key patterns

- **Pydantic models** (`models.py`) define all data structures — always use them, never raw dicts
- **Provider abstraction** (`providers/base.py`) — all providers implement `run_agent()` and `run_judge()`
- **Config** (`config.py`) — single `MobiusConfig` object, loaded via `get_config()`
- **Database** (`db.py`) — raw SQLite with WAL mode, no ORM. Helpers convert rows to Pydantic models
- **Async execution** — `swarm.py` uses `asyncio` with semaphore-based concurrency control

## Module dependency graph

```
cli.py
  └── orchestrator.py
        ├── selector.py → memory.py → embedder.py
        ├── swarm.py → runner.py → providers/*.py
        ├── judge.py → runner.py
        └── tournament.py
              └── db.py → models.py
```

## Adding a new provider

1. Create `src/mobius/providers/yourprovider.py`
2. Subclass `Provider` from `base.py`
3. Implement `run_agent(agent, task) -> str` and `run_judge(model, system_prompt, user_prompt) -> str`
4. Register it in `runner.py`'s provider dispatch
5. Add the provider name to `ProviderType` literal in `models.py`

## Adding a new CLI command

1. Add command function in `cli.py` using `@app.command()`
2. Use `get_config()` for settings, `get_db()` for database access
3. Follow existing patterns: init db connection, run logic, display with Rich

## Testing conventions

- Tests in `tests/` using pytest
- Use in-memory SQLite (`:memory:`) for isolation
- Async tests auto-detected via `asyncio_mode = "auto"` in pyproject.toml
- `/mobius-audit` skill for end-to-end verification (quick/full/interactive modes)

## Skills

Skills live in `.claude/skills/` and provide free Opus-powered workflows:

| Skill | Trigger | What it does |
|-------|---------|-------------|
| `/mobius-seed` | "seed agents", "bootstrap" | Creates agents directly (free, no API) |
| `/mobius-run` | "compete", "run" | Runs a competition from Claude Code |
| `/mobius-judge` | "judge this" | Evaluates match outputs (free, no API) |
| `/mobius-audit` | "audit", "health check" | Verifies system health, finds bugs |

Each skill has a `SKILL.md` (instructions) and optional `scripts/` (helper scripts the skill invokes).

## Files agents should NOT modify

- `data/mobius.db` — runtime database, managed by the application
- `.env` — contains API secrets
- `data/*.html` — generated competition outputs

## Common tasks

| Task | Where to look |
|------|--------------|
| Change agent selection logic | `selector.py` |
| Modify judging criteria | `judge.py` (system prompt) |
| Adjust Elo math | `tournament.py` |
| Add provider support | `providers/`, `runner.py`, `models.py` |
| Change swarm behavior | `swarm.py` |
| Modify agent creation | `agent_builder.py` |
| Update data models | `models.py`, then `db.py` schema |
