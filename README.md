<div align="center">

# Mobius

**What if your AI agents competed to get better — automatically?**

Mobius is an adversarial swarm orchestrator that pits AI agents against each other,
judges them with a cross-family panel, and evolves the winners — across Anthropic, Google, and OpenAI.

<!-- Update AaronGoldsmith after pushing to GitHub -->
[![CI](https://github.com/AaronGoldsmith/mobius/actions/workflows/ci.yml/badge.svg)](https://github.com/AaronGoldsmith/mobius/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

Most agent frameworks run one model, hope for the best, and call it done. Mobius takes a different approach: **competition drives quality.**

- **5 agents** tackle every task in parallel — different providers, different strategies
- **3 judges** from different model families score the outputs (no home-field advantage)
- **Elo ratings** track who's actually good, not who's hyped
- **Evolution** breeds winners into new variants; underperformers get retired
- **Memory** remembers which agents won on similar tasks, so selection gets smarter over time

```
Task → Selector → Swarm (parallel) → Judge Panel → Elo Update → Memory
                                                         ↓
                                              Evolve / Retire / Promote
```

## Quick start

```bash
pip install -e ".[dev]"
cp .env.example .env          # Add your API keys
mobius init                    # Create database
mobius bootstrap               # Seed agents (~$1.50) — or /mobius-seed for free
mobius run "Build a CLI that converts CSV to JSON"
```

## Demo

<!-- Replace with an actual screenshot or terminal recording (asciinema/vhs) -->
<!-- Run: mobius run "your task" and capture the Rich UI output -->

> *Placeholder — add a screenshot or [asciinema](https://asciinema.org/) recording of a real competition here.*

## Why Mobius?

| Problem | How Mobius solves it |
|---------|---------------------|
| "Which model is best for X?" | Run them all. Let judges decide per-task. |
| Model outputs vary wildly | 5 attempts + consensus judging smooths variance |
| No ground truth for creative tasks | Cross-family panel eliminates single-model bias |
| Agents degrade silently | Elo tracks performance over time; losers get evolved or retired |
| Selection is manual guesswork | Vector memory recalls what worked on similar past tasks |

## Commands

```bash
mobius run "task"               # Run a competition
mobius loop --rounds 10         # Self-improvement loop
mobius leaderboard              # Elo rankings
mobius scout ./src              # Auto-generate domain agents from your code
mobius evolve backend           # Improve underperformers in a specialization
mobius explain                  # Show last match's judge reasoning
mobius stats                    # Overview
mobius agent list               # Browse agents
mobius agent show <slug>        # Agent details
```

## How it works

### Agents

Agents are stored in a SQLite registry with system prompts, provider configs, and Elo ratings. Each agent has:
- A **provider** (Anthropic, Google, OpenAI, OpenRouter)
- A **specialization** (backend, frontend, algorithms, etc.)
- An **Elo rating** that updates after every match
- A **generation** — evolved agents track their lineage

### Selection

Three strategies pick agents for each competition:
- **Specialist** — top performers on similar past tasks (memory-driven)
- **Diverse** — maximize provider and specialization variety
- **Ensemble** — balanced mix of both

### Judging

A panel of three models from different families scores each output on correctness, quality, and completeness. Consensus scoring prevents any single provider from biasing results.

### Evolution

After every N matches, Mobius:
1. Identifies underperformers (low win rate over recent matches)
2. Takes the best agents and breeds refined variants via Opus
3. Retires agents on long losing streaks
4. Promotes consistent winners to champion status

## Architecture

```
src/mobius/
├── cli.py              # Typer CLI
├── orchestrator.py     # Competition coordinator
├── swarm.py            # Async parallel execution
├── runner.py           # Provider dispatcher
├── judge.py            # Cross-family judge panel
├── tournament.py       # Elo rating system
├── selector.py         # Agent selection strategies
├── memory.py           # Vector similarity (sqlite-vec)
├── registry.py         # Agent CRUD
├── agent_builder.py    # Opus-powered agent creation
├── models.py           # Pydantic data models
├── config.py           # Configuration
└── providers/
    ├── base.py         # Abstract interface
    ├── anthropic.py    # Claude models
    ├── google.py       # Gemini models
    ├── openai.py       # GPT models
    └── openrouter.py   # Multi-model gateway
```

## Cost

Mobius is designed to be cheap to run:

| What | Model tier | Cost |
|------|-----------|------|
| Swarm execution | Haiku / Flash / GPT-4o-mini | ~$0.01-0.05 per agent |
| Judge panel (API) | Opus + Gemini Pro + GPT-4o | ~$0.10 per match |
| Full competition | 5 agents + 3 judges | ~$0.15-0.35 |
| Bootstrap (one-time) | Opus | ~$1.50 |

**Claude Code users**: `/mobius-seed` and `/mobius-judge` use your Opus subscription directly — same quality, zero API cost.

## Configuration

| Env variable | Default | What it does |
|-------------|---------|--------------|
| `MOBIUS_DATA_DIR` | `data` | Where the database lives |
| `MOBIUS_SWARM_SIZE` | `5` | Agents per competition |
| `MOBIUS_BUDGET_USD` | `50.0` | Global spending cap |

See [`config.py`](src/mobius/config.py) for all tunable parameters.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
