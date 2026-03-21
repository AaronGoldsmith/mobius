# Mobius

Adversarial agent swarm orchestrator with multi-provider support.

## Quick Start

```bash
pip install -e ".[dev]"
mobius init
mobius bootstrap      # OR use /mobius-seed for free Opus-powered seeding
mobius run "your task here"
```

## Architecture

- **Python 3.12+** with claude-agent-sdk, openai, google-genai
- **SQLite + sqlite-vec** for agent registry and vector memory
- **Multi-provider**: Agents can be Anthropic, Google, or OpenAI
- **Cross-family judges**: Claude Opus + Gemini Pro + GPT-4o panel
- **Hybrid smart model**: Claude Code Opus (free via Pro sub) handles agent creation and judging via skills; API calls only for cheap swarm execution and cross-family diversity

## Key Insight: Skills as the Smart Model Layer

Your Claude Code Opus is the same model as the API's Opus — but free on Pro. So:
- `/mobius-seed` — Opus creates agents directly (free, uses your full context)
- `/mobius-judge` — Opus judges competition outputs (free, same quality)
- `agent_builder.py` — Opus via API (costs money, for automated loops)
- `mobius run` — Haiku/Flash swarm via API (cheap, parallel execution)

## CLI Commands

- `mobius init` — Initialize database
- `mobius run "task"` — Run a competition (`--sandbox` for Docker isolation)
- `mobius bootstrap` — Seed agents via API (costs ~$1.50)
- `mobius scout <path>` — Auto-generate domain-specific agents
- `mobius evolve <spec>` — Improve agents via feedback
- `mobius leaderboard` — View Elo rankings
- `mobius explain` — Show last match's judge reasoning
- `mobius loop --rounds N` — Self-improvement loop across varied tasks
- `mobius train "challenge" --rounds N` — Iterative training on a single challenge (refines losers each round)
- `mobius stats` — Overview statistics

## Skills (Free via Pro subscription)

- `/mobius-seed [spec]` — Opus creates agents directly (you ARE the builder)
- `/mobius-run <task>` — Run a competition from Claude Code
- `/mobius-judge` — Opus judges latest match outputs (free)
- `/mobius-audit [quick|full|interactive]` — Health check, end-to-end verification, guided exploration

## Sandbox Mode

Agents can run inside disposable Docker containers for isolation and safety:

```bash
mobius run "task" --sandbox           # per-run
MOBIUS_SANDBOX=true mobius run "task"  # env var
```

Requires Docker. Each competition spins up a `python:3.12-slim` container with no network access, 512MB memory limit, and `/workspace` as the working directory. Container is destroyed after each competition.

Configure via `MobiusConfig`: `sandbox_image`, `sandbox_memory_limit`, `sandbox_network`.

## Testing

```bash
pytest tests/ -v
mobius-audit quick    # or use /mobius-audit from Claude Code
```
