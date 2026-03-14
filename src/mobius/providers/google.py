"""Google Gemini provider."""

from __future__ import annotations

import asyncio
import logging
import os

from mobius.providers.base import Provider, ProviderResult

logger = logging.getLogger(__name__)


def _get_api_key() -> str | None:
    """Get Google API key from various env var names."""
    for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY"):
        key = os.environ.get(var)
        if key:
            return key
    return None


class GoogleProvider(Provider):
    """Run agents and judges via Google Gemini API."""

    @property
    def name(self) -> str:
        return "google"

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
        """Execute via Google GenAI SDK."""
        api_key = _get_api_key()
        if not api_key:
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error="No Google API key (set GOOGLE_API_KEY or GEMINI_API_KEY)",
            )

        try:
            from google import genai
        except ImportError:
            return ProviderResult(
                output="",
                model=model,
                provider=self.name,
                error="google-genai not installed",
            )

        try:
            client = genai.Client(api_key=api_key)

            full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=full_prompt,
                ),
                timeout=timeout_seconds,
            )

            output = response.text or ""
            tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

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
            logger.error("Google agent error: %s", e)
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
        """Run judge evaluation via Gemini."""
        return await self.run_agent(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            timeout_seconds=timeout_seconds,
        )
