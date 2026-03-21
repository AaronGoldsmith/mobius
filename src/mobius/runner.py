"""Provider dispatcher: routes agent execution to the correct provider."""

from __future__ import annotations

import logging
import os
import platform

from mobius.models import AgentRecord, ProviderType
from mobius.providers.anthropic import AnthropicProvider
from mobius.providers.base import Provider, ProviderResult
from mobius.providers.google import GoogleProvider
from mobius.providers.openai import OpenAIProvider
from mobius.providers.openrouter import OpenRouterProvider
from mobius.providers.tools import get_current_sandbox

logger = logging.getLogger(__name__)

_PLATFORM = platform.system()
# subprocess.run(shell=True) uses /bin/sh (POSIX) or %COMSPEC% (Windows),
# not necessarily $SHELL, so report what agents will actually execute under.
_SHELL = "cmd.exe" if _PLATFORM == "Windows" else "/bin/sh"

# Only list tools that providers actually implement.  Currently all providers
# gate on "Bash" — other names (Read, Write, etc.) exist in agent records
# but aren't wired up, so advertising them would mislead the model.
_IMPLEMENTED_TOOLS: set[str] = {"Bash"}

_BASH_EXAMPLES = (
    "dir, type, findstr, git, etc."
    if _PLATFORM == "Windows"
    else "ls, cat, grep, git, etc."
)

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "Bash": f"run shell commands ({_BASH_EXAMPLES})",
    "Read": "read file contents",
    "Write": "create or overwrite files",
    "Edit": "edit files with find-and-replace",
    "Grep": "search file contents with regex",
    "Glob": "find files by name pattern",
}

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


_PLATFORM_LINE = f"Platform: {_PLATFORM} (shell: {_SHELL})"


def _build_context_prefix(agent: AgentRecord, working_dir: str) -> str:
    """Build an environment context string so agents know what they can do."""
    if get_current_sandbox():
        lines = [
            "Working directory: /workspace",
            "Platform: Linux (sandboxed Docker container)",
        ]
    else:
        lines = [
            f"Working directory: {os.path.basename(working_dir)}",
            _PLATFORM_LINE,
        ]

    # Only advertise tools that are actually wired up in providers.
    tools = [t for t in (agent.tools or []) if t in _IMPLEMENTED_TOOLS]
    if tools:
        available = [_TOOL_DESCRIPTIONS.get(t, t) for t in tools]
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

    result = await provider.run_agent(
        prompt=prompt,
        system_prompt=agent.system_prompt,
        model=agent.model,
        tools=agent.tools,
        max_turns=agent.max_turns,
        max_budget_usd=max_budget_usd,
        timeout_seconds=timeout_seconds,
        working_dir=working_dir,
    )

    logger.info(
        "Agent %s finished: success=%s turns=%d output=%d chars tokens=%d/%d",
        agent.slug,
        result.success,
        result.turns_used,
        len(result.output),
        result.tokens_in,
        result.tokens_out,
    )
    if result.error:
        logger.warning("Agent %s error: %s", agent.slug, result.error)

    return result


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
