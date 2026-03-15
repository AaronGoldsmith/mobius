"""Provider dispatcher: routes agent execution to the correct provider."""

from __future__ import annotations

import logging
import os

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


def _build_context_prefix(agent: AgentRecord, working_dir: str) -> str:
    """Build an environment context string so agents know what they can do."""
    lines = [f"Working directory: {working_dir}"]

    tools = agent.tools or []
    if tools:
        tool_descriptions = {
            "Bash": "run shell commands (ls, cat, grep, git, etc.)",
            "Read": "read file contents",
            "Grep": "search file contents with regex",
            "Glob": "find files by name pattern",
        }
        available = [tool_descriptions.get(t, t) for t in tools]
        lines.append(f"Available tools: {', '.join(available)}")

    return "\n".join(lines)


async def run_agent(
    agent: AgentRecord,
    task: str,
    working_dir: str | None = None,
    timeout_seconds: int = 120,
    max_budget_usd: float = 0.05,
) -> ProviderResult:
    """Run an agent on a task via its configured provider."""
    provider = get_provider(agent.provider)
    working_dir = working_dir or os.getcwd()

    logger.info(
        "Running agent %s (%s/%s) on task",
        agent.slug,
        agent.provider,
        agent.model,
    )

    # Inject environment context so agents know where they are and what
    # tools they have, rather than asking the user for URLs or access.
    context = _build_context_prefix(agent, working_dir)
    prompt = f"[Environment]\n{context}\n\n[Task]\n{task}"

    return await provider.run_agent(
        prompt=prompt,
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
