"""Global configuration for Mobius."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


class MobiusConfig(BaseModel):
    """All tunable settings in one place."""

    # Paths
    data_dir: Path = Path("data")
    db_name: str = "mobius.db"
    log_name: str = "mobius.log"
    claude_agents_dir: Path = Path(".claude/agents")

    # Swarm
    swarm_size: int = 5
    swarm_concurrency: int = 5
    agent_timeout_seconds: int = 120
    agent_max_turns: int = 10
    agent_budget_usd: float = 0.05
    agent_max_output_tokens: int = 16384

    # Judge
    judge_models: list[dict[str, str]] = [
        {"provider": "anthropic", "model": "claude-opus-4-6"},
        {"provider": "google", "model": "gemini-2.5-pro"},
        {"provider": "openai", "model": "gpt-4o"},
    ]

    # Tournament
    elo_k_factor: int = 32
    elo_default: float = 1500.0
    promotion_wins_required: int = 3
    promotion_matches: int = 5

    # Memory
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    memory_top_k: int = 5
    similarity_specialist_threshold: float = 0.5
    similarity_ensemble_threshold: float = 0.3

    # Self-improvement
    max_agent_population: int = 50
    underperformer_win_rate: float = 0.4
    underperformer_window: int = 20
    evolve_every_n_matches: int = 20
    retirement_loss_streak: int = 50

    # Budget
    global_budget_usd: float = 50.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def log_path(self) -> Path:
        return self.data_dir / self.log_name


def _load_dotenv() -> None:
    """Load .env file if it exists, without overwriting existing env vars."""
    for env_path in [Path(".env"), Path.home() / ".env"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                # Don't overwrite existing env vars
                if key and not os.environ.get(key):
                    os.environ[key] = value


def get_config() -> MobiusConfig:
    """Load config, with env var overrides for key settings."""
    _load_dotenv()
    config = MobiusConfig()

    if val := os.environ.get("MOBIUS_DATA_DIR"):
        config.data_dir = Path(val)
    if val := os.environ.get("MOBIUS_SWARM_SIZE"):
        config.swarm_size = int(val)
    if val := os.environ.get("MOBIUS_BUDGET_USD"):
        config.global_budget_usd = float(val)

    return config
