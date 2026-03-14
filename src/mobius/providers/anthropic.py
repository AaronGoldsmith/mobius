"""Anthropic provider using the messages API directly."""

from __future__ import annotations

import asyncio
import logging
import os

from mobius.providers.base import Provider, ProviderResult

logger = logging.getLogger(__name__)


def _get_api_key() -> str | None:
    """Get Anthropic API key, falling back to Claude Code session token."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    # Claude Code exposes a session token that works as an API key
    session_token = os.environ.get("CLAUDE_CODE_SESSION_ACCESS_TOKEN")
    if session_token:
        logger.info("Using Claude Code session token as Anthropic API key")
        return session_token
    return None


class AnthropicProvider(Provider):
    """Run agents via the Anthropic messages API."""

    @property
    def name(self) -> str:
        return "anthropic"

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
        """Execute via Anthropic messages API.

        Uses the messages API directly instead of claude-agent-sdk to avoid
        the nested Claude Code session issue.
        """
        try:
            import anthropic
        except ImportError:
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error="anthropic SDK not installed",
            )

        api_key = _get_api_key()
        if not api_key:
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error="No Anthropic API key found (set ANTHROPIC_API_KEY or run inside Claude Code)",
            )

        try:
            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await asyncio.wait_for(
                client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=timeout_seconds,
            )

            output = ""
            for block in response.content:
                if hasattr(block, "text"):
                    output += block.text

            return ProviderResult(
                output=output,
                model=model,
                provider=self.name,
                tokens_in=response.usage.input_tokens,
                tokens_out=response.usage.output_tokens,
            )

        except asyncio.TimeoutError:
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error=f"Timeout after {timeout_seconds}s",
                truncated=True,
            )
        except Exception as e:
            logger.error("Anthropic agent error: %s", e)
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error=str(e),
            )

    async def run_judge(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_budget_usd: float = 0.15,
        timeout_seconds: int = 120,
    ) -> ProviderResult:
        """Run judge via Anthropic messages API."""
        return await self.run_agent(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            timeout_seconds=timeout_seconds,
        )
