"""OpenRouter provider — access many models through a single API."""

from __future__ import annotations

import asyncio
import logging
import os

from mobius.providers.base import Provider, ProviderResult

logger = logging.getLogger(__name__)


class OpenRouterProvider(Provider):
    """Run agents and judges via OpenRouter (OpenAI-compatible API)."""

    BASE_URL = "https://openrouter.ai/api/v1"

    @property
    def name(self) -> str:
        return "openrouter"

    def _get_api_key(self) -> str | None:
        return os.environ.get("OPENROUTER_API_KEY")

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
        """Execute via OpenRouter (OpenAI-compatible endpoint)."""
        api_key = self._get_api_key()
        if not api_key:
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error="No OPENROUTER_API_KEY set",
            )

        try:
            from openai import AsyncOpenAI
        except ImportError:
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error="openai SDK not installed (needed for OpenRouter compatibility)",
            )

        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.BASE_URL,
            )

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
            logger.error("OpenRouter agent error: %s", e)
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
        """Run judge evaluation via OpenRouter."""
        return await self.run_agent(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            timeout_seconds=timeout_seconds,
        )
