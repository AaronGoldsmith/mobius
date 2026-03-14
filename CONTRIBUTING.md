# Contributing to Mobius

Thanks for your interest in Mobius. Here's how to get started.

## Setup

```bash
git clone https://github.com/AaronGoldsmith/mobius.git
cd mobius
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
cp .env.example .env       # add at least one API key
mobius init
```

## Development workflow

1. Create a branch from `main`
2. Make your changes
3. Run `pytest tests/ -v` to verify
4. Open a PR against `main`

## Code style

- Python 3.12+ — use modern syntax (type unions with `|`, etc.)
- Pydantic models for all data structures — no raw dicts crossing module boundaries
- Async where it touches the network (providers, swarm execution)
- Keep modules focused — one responsibility per file

## Adding a provider

1. Create `src/mobius/providers/yourprovider.py`
2. Subclass `Provider` from `base.py`
3. Implement `run_agent()` and `run_judge()`
4. Register it in `runner.py`
5. Add the provider name to `ProviderType` in `models.py`

## Adding a CLI command

1. Add a `@app.command()` function in `cli.py`
2. Use `get_config()` and `get_db()` for setup
3. Use Rich for terminal output

## Tests

- Use in-memory SQLite (`:memory:`) for test isolation
- Place tests in `tests/`
- Async tests are auto-detected (no decorator needed)

## Reporting issues

Open an issue with:
- What you expected
- What happened
- Steps to reproduce
- Python version and OS
