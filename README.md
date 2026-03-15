<div align="center">

# Mobius

**What if your AI agents competed to get better — automatically?**

Mobius is an adversarial swarm orchestrator that pits AI agents against each other,
judges them with a cross-family panel, and evolves the winners — across Anthropic, Google, and OpenAI.

[![CI](https://github.com/AaronGoldsmith/mobius/actions/workflows/ci.yml/badge.svg)](https://github.com/AaronGoldsmith/mobius/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

Most agent frameworks run one model, hope for the best, and call it done. Mobius takes a different approach: **run multiple agents in parallel, have independent judges score them, and evolve the winners.**

- **5 agents** (configurable) tackle every task in parallel — different providers, different strategies
- **3 judges** from different model families score the outputs (reduces single-provider bias)
- **Elo ratings** track who's actually good, not who's hyped
- **Evolution** breeds winners into new variants; underperformers get retired
- **Memory** remembers which agents won on similar tasks, so selection gets smarter over time

**When Mobius is worth it:**
- You're uncertain which model/provider is best for your task
- Output quality varies between runs and you need consistency
- You want long-term performance tracking as models change
- You're willing to spend 3-5x more tokens for statistically better outputs

For simple tasks with predictable outputs, a single good model is fine. Mobius is for problems where consistency and optimization matter.

```
Task → Memory Query → Selector → Swarm (parallel) → Judge Panel → Elo Update
                                                           ↓
                                                Evolve / Retire / Promote
```

## Quick start

### Prerequisites

- **Python 3.12+**
- At least one LLM API key (Anthropic recommended — required for the default judge panel):
  - **Anthropic** (Claude) — recommended, used by default judge panel
  - **Google** (Gemini) — optional, adds provider diversity
  - **OpenAI** (GPT) — optional, adds provider diversity
- **Claude Code Pro/Team** — optional, enables free agent seeding and judging via skills

### Install & run

```bash
pip install -e ".[dev]"
cp .env.example .env          # Add your API keys (see .env.example for all options)
mobius init                    # Create database
```

Bootstrap agents (choose one):

```bash
# Option A: API-driven (~$1.50 one-time cost, automated)
mobius bootstrap

# Option B: Claude Code (free, requires Pro/Team subscription)
# In Claude Code, type: /mobius-seed

# Option C: Domain-specific (uses Opus API to analyze your codebase, ~$0.50)
mobius scout ./my-project --count 5
```

Run your first competition:

```bash
mobius run "Build a CLI that converts CSV to JSON"
```

## Demo

```
$ mobius run "Write a Python LRU Cache with O(1) operations"

Starting competition (19 agents in pool, selecting best 5)
Strategy: diverse (memory matches: 3)
  Gemini Flash Coder (google/gemini-2.5-flash)
  GPT Mini Coder (openai/gpt-4o-mini)
  Methodical Coder (anthropic/claude-haiku-4-5)
  OpenRouter Wildcard (openrouter/gemini-2.5-flash)       (wildcard)

┌──────────────────────┬────────────┬──────────────┬───────────┐
│ Agent                │ Provider   │ Status       │ Preview   │
├──────────────────────┼────────────┼──────────────┼───────────┤
│ Gemini Flash Coder   │ google     │ completed    │ class LRU │
│ GPT Mini Coder       │ openai     │ completed    │ from coll │
│ Methodical Coder     │ anthropic  │ completed    │ class Nod │
│ OpenRouter Wildcard  │ openrouter │ completed    │ import co │
└──────────────────────┴────────────┴──────────────┴───────────┘

┌─────────────── Judge Panel ───────────────┐
│ Agent               │ Score │ Winner      │
├─────────────────────┼───────┼─────────────┤
│ Gemini Flash Coder  │  29.0 │   WINNER    │
│ GPT Mini Coder      │  24.0 │             │
│ Methodical Coder    │  22.0 │             │
│ OpenRouter Wildcard │  22.0 │             │
└─────────────────────┴───────┴─────────────┘

$ mobius scout ./my-project --count 5
Scouting ./my-project...
  Read: README.md, pyproject.toml, CLAUDE.md
  Sampled: 5 source files
Created: Protocol Engineer (anthropic/claude-sonnet-4-6)   specs=[coding, architecture]
Created: Test Specialist (anthropic/claude-sonnet-4-6)     specs=[testing, debugging]
Created: Dashboard Dev (anthropic/claude-sonnet-4-6)       specs=[frontend, coding]
Created: Spec Auditor (anthropic/claude-sonnet-4-6)        specs=[security, code-review]
Created: Perf Optimizer (google/gemini-2.5-flash)          specs=[backend, algorithms]

Scout created 5 agents for my-project.
```

> Record your own: `asciinema rec demo.cast` then run some competitions. Scripts in `scripts/`.

## Why Mobius?

| Problem | How Mobius solves it | Trade-off |
|---------|---------------------|-----------|
| Which model is best? | Run all in parallel; judges pick best per task | 3-5x token cost vs. single call |
| High output variance | Consensus scoring from 3 judges reduces outliers | Judge disagreement requires tiebreaker logic |
| Creative tasks lack ground truth | Cross-provider judges (Claude + Gemini + GPT) reduce vendor bias | Judges add ~$0.10 per match |
| Agents degrade silently | Elo tracks performance over time; losers get evolved or retired | Requires match history; cold start is random |
| Selection is manual guesswork | Vector memory recalls what worked on similar past tasks | Embedding similarity isn't perfect for all task types |

## Commands

```bash
mobius run "task"               # Run a competition
mobius train "task" --rounds 5  # Iterative training on a single challenge
mobius loop --rounds 10         # Self-improvement loop across varied tasks
mobius leaderboard              # Elo rankings
mobius scout ./src              # Auto-generate domain agents from your code
mobius evolve backend           # Improve underperformers in a specialization
mobius explain                  # Show last match's judge reasoning
mobius stats                    # Overview
mobius agent list               # Browse agents
mobius agent show <slug>        # Agent details
mobius agent export <slug>      # Export agent as .claude/agents/ markdown
```

## Claude Code Skills (Free)

If you use [Claude Code](https://claude.com/claude-code) with a Pro/Team subscription, these skills replace the paid API equivalents:

| Skill | Replaces | What it does |
|-------|----------|-------------|
| `/mobius-seed` | `mobius bootstrap` | Opus creates agents directly — same quality, $0 |
| `/mobius-run --free` | `mobius run` | Haiku subagents compete, Opus judges — $0 |
| `/mobius-judge` | API judge panel | Opus evaluates outputs locally — $0 |
| `/mobius-audit` | manual testing | Health checks and guided exploration |

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
2. Refines underperformers using judge feedback via Opus
3. Retires agents on long losing streaks
4. Promotes consistent winners to champion status

### Memory

After each competition, the winning agent's task is embedded (all-MiniLM-L6-v2) and stored. Future selections query this vector memory to find agents that won on similar past tasks — so the system gets smarter with every match.

## Architecture

### Request → Execution → Judgment → Learning

```
┌─────────────────────────────────────────────────────────────┐
│ CLI (cli.py) — Typer command handlers                       │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Orchestrator (orchestrator.py) — Coordinates a match        │
│  1. Select agents via selector.py (uses memory.py)          │
│  2. Run agents in parallel via swarm.py                     │
│  3. Judge outputs via judge.py + runner.py                  │
│  4. Update Elo ratings via tournament.py                    │
│  5. Log results to database (db.py)                         │
└─────────────────────────────────────────────────────────────┘
```

**Provider abstraction** — All model calls go through `providers/` (anthropic, google, openai, openrouter), each implementing the same async interface with concurrency control.

**Data layer** — Pydantic models (`models.py`), SQLite with WAL mode (`db.py`), agent CRUD (`registry.py`), and vector similarity via sqlite-vec (`memory.py` + local Sentence-Transformers embeddings).

**Evolution** — `agent_builder.py` uses Opus to create/refine agents; `tournament.py` handles Elo math; `selector.py` picks agents via Specialist, Diverse, or Ensemble strategies.

## Cost

Costs below are for typical tasks (500-2000 tokens per agent attempt):

| Component | Models | Cost | Notes |
|-----------|--------|------|-------|
| Swarm (5 agents) | Haiku / Flash / GPT-4o-mini | ~$0.01-0.05 | Parallel; scales with task length |
| Judge panel | Opus + Gemini Pro + GPT-4o | ~$0.05-0.15 | Evaluates all 5 outputs |
| Full competition | 5 agents + 3 judges | ~$0.10-0.25 | One round |
| Bootstrap (one-time) | Opus | ~$1.50 | Creates initial agent pool |
| Scout | Opus | ~$0.50 | Analyzes codebase, creates domain agents |
| Vector embeddings | Sentence-Transformers | $0 | Runs locally, no API cost |

**Claude Code users**: `/mobius-seed` and `/mobius-judge` use your Opus subscription directly — same quality, zero API cost. CLI commands (`mobius run`, `mobius bootstrap`, `mobius scout`) still require API keys.

*Costs estimated March 2026. Verify current pricing in your provider dashboards.*

## Configuration

| Env variable | Default | What it does |
|-------------|---------|--------------|
| `MOBIUS_DATA_DIR` | `data` | Where the database lives |
| `MOBIUS_SWARM_SIZE` | `5` | Agents per competition |
| `MOBIUS_BUDGET_USD` | `50.0` | Global spending cap |

These are the env-overridable settings. Additional parameters (Elo K-factor, promotion thresholds, embedding model, evolution triggers, retirement streaks, and more) can be tuned directly in [`config.py`](src/mobius/config.py).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
