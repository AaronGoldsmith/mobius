"""Abstract provider interface for multi-model support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProviderResult:
    """Result from running an agent via any provider."""

    output: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    truncated: bool = False
    turns_used: int = 0

    @property
    def success(self) -> bool:
        return self.error is None and len(self.output.strip()) > 0


class Provider(ABC):
    """Abstract base for model providers."""

    @abstractmethod
    async def run_agent(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        tools: list[str] | None = None,
        max_turns: int = 10,
        max_budget_usd: float = 0.05,
        timeout_seconds: int = 120,
        working_dir: str | None = None,
    ) -> ProviderResult:
        """Execute an agent and return its output."""
        ...

    @abstractmethod
    async def run_judge(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_budget_usd: float = 0.15,
        timeout_seconds: int = 120,
    ) -> ProviderResult:
        """Run a judge evaluation (no tools, expects structured output)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name: 'anthropic', 'google', 'openai'."""
        ...
