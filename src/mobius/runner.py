"""Provider dispatcher: routes agent execution to the correct provider."""

from __future__ import annotations

import logging

from mobius.models import AgentRecord, ProviderType
from mobius.providers.anthropic import AnthropicProvider
from mobius.providers.base import Provider, ProviderResult
from mobius.providers.google import GoogleProvider
from mobius.providers.openai import OpenAIProvider
from mobius.providers.openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)

# Singleton provider instances
_providers: dict[str, Provider] = {}


def get_provider(provider_name: ProviderType) -> Provider:
    """Get or create a provider instance."""
    if provider_name not in _providers:
        match provider_name:
            case "anthropic":
                _providers[provider_name] = AnthropicProvider()
            case "google":
                _providers[provider_name] = GoogleProvider()
            case "openai":
                _providers[provider_name] = OpenAIProvider()
            case "openrouter":
                _providers[provider_name] = OpenRouterProvider()
            case _:
                raise ValueError(f"Unknown provider: {provider_name}")
    return _providers[provider_name]


async def run_agent(
    agent: AgentRecord,
    task: str,
    working_dir: str | None = None,
    timeout_seconds: int = 120,
    max_budget_usd: float = 0.05,
) -> ProviderResult:
    """Run an agent on a task via its configured provider."""
    provider = get_provider(agent.provider)

    logger.info(
        "Running agent %s (%s/%s) on task",
        agent.slug,
        agent.provider,
        agent.model,
    )

    return await provider.run_agent(
        prompt=task,
        system_prompt=agent.system_prompt,
        model=agent.model,
        tools=agent.tools,
        max_turns=agent.max_turns,
        max_budget_usd=max_budget_usd,
        timeout_seconds=timeout_seconds,
        working_dir=working_dir,
    )


async def run_judge(
    prompt: str,
    system_prompt: str,
    provider_name: ProviderType,
    model: str,
    max_budget_usd: float = 0.15,
    timeout_seconds: int = 120,
) -> ProviderResult:
    """Run a judge evaluation via the specified provider."""
    provider = get_provider(provider_name)

    logger.info("Running judge (%s/%s)", provider_name, model)

    return await provider.run_judge(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        max_budget_usd=max_budget_usd,
        timeout_seconds=timeout_seconds,
    )
