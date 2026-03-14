"""OpenAI provider."""

from __future__ import annotations

import asyncio
import logging

from mobius.providers.base import Provider, ProviderResult

logger = logging.getLogger(__name__)


class OpenAIProvider(Provider):
    """Run agents and judges via OpenAI API."""

    @property
    def name(self) -> str:
        return "openai"

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
        """Execute via OpenAI chat completions."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error="openai SDK not installed",
            )

        try:
            client = AsyncOpenAI()

            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=4096,
                ),
                timeout=timeout_seconds,
            )

            output = response.choices[0].message.content or ""
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0

            return ProviderResult(
                output=output,
                model=model,
                provider=self.name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
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
            logger.error("OpenAI agent error: %s", e)
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
        """Run judge evaluation via OpenAI."""
        return await self.run_agent(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            timeout_seconds=timeout_seconds,
        )
