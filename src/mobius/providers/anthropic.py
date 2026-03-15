"""Anthropic provider using the messages API with optional tool use."""

from __future__ import annotations

import asyncio
import logging
import os

from mobius.providers.base import Provider, ProviderResult
from mobius.providers.tools import ANTHROPIC_BASH_TOOL, run_command

logger = logging.getLogger(__name__)


def _get_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY")


class AnthropicProvider(Provider):
    """Anthropic provider via messages API.

    When tools are requested, runs an agentic loop with native tool use
    (bash). Otherwise, single-shot message like every other provider.
    """

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
        """Run via Anthropic messages API, with tool loop if tools requested."""
        api_key = _get_api_key()
        if not api_key:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error="No ANTHROPIC_API_KEY set",
            )

        try:
            import anthropic
        except ImportError:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error="anthropic SDK not installed",
            )

        client = anthropic.AsyncAnthropic(api_key=api_key)
        use_tools = tools and "Bash" in tools

        if use_tools:
            return await self._run_with_tools(
                client, prompt, system_prompt, model,
                max_turns, timeout_seconds, working_dir,
            )
        else:
            return await self._run_simple(
                client, prompt, system_prompt, model, timeout_seconds,
            )

    async def _run_simple(
        self, client, prompt: str, system_prompt: str,
        model: str, timeout_seconds: int,
    ) -> ProviderResult:
        """Single-shot message, same as Google/OpenAI providers."""
        try:
            response = await asyncio.wait_for(
                client.messages.create(
                    model=model, max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=timeout_seconds,
            )
            output = "".join(
                b.text for b in response.content if hasattr(b, "text")
            )
            return ProviderResult(
                output=output, model=model, provider=self.name,
                tokens_in=response.usage.input_tokens,
                tokens_out=response.usage.output_tokens,
            )
        except asyncio.TimeoutError:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error=f"Timeout after {timeout_seconds}s", truncated=True,
            )
        except Exception as e:
            logger.error("Anthropic error: %s", e)
            return ProviderResult(
                output="", model=model, provider=self.name, error=str(e),
            )

    async def _run_with_tools(
        self, client, prompt: str, system_prompt: str,
        model: str, max_turns: int, timeout_seconds: int,
        working_dir: str | None = None,
    ) -> ProviderResult:
        """Agentic loop with bash tool use."""
        messages = [{"role": "user", "content": prompt}]
        total_in, total_out = 0, 0
        text_outputs: list[str] = []
        turn = 0

        try:
            for turn in range(max_turns):
                response = await asyncio.wait_for(
                    client.messages.create(
                        model=model, max_tokens=4096,
                        system=system_prompt,
                        messages=messages,
                        tools=[ANTHROPIC_BASH_TOOL],
                    ),
                    timeout=timeout_seconds,
                )
                total_in += response.usage.input_tokens
                total_out += response.usage.output_tokens

                for block in response.content:
                    if hasattr(block, "text") and block.text:
                        text_outputs.append(block.text)

                if response.stop_reason != "tool_use":
                    break

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use" and block.name == "bash":
                        cmd = block.input.get("command", "")
                        logger.info("Agent running: %s", cmd[:100])
                        result = await asyncio.to_thread(
                            run_command, cmd, timeout=30,
                            working_dir=working_dir,
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            return ProviderResult(
                output="\n".join(text_outputs), model=model, provider=self.name,
                tokens_in=total_in, tokens_out=total_out,
                turns_used=min(turn + 1, max_turns),
            )
        except asyncio.TimeoutError:
            return ProviderResult(
                output="\n".join(text_outputs), model=model, provider=self.name,
                error=f"Timeout after {timeout_seconds}s", truncated=True,
                tokens_in=total_in, tokens_out=total_out,
            )
        except Exception as e:
            logger.error("Anthropic tools error: %s", e)
            return ProviderResult(
                output="\n".join(text_outputs), model=model, provider=self.name,
                error=str(e), tokens_in=total_in, tokens_out=total_out,
            )

    async def run_judge(
        self, prompt: str, system_prompt: str, model: str,
        max_budget_usd: float = 0.15, timeout_seconds: int = 120,
    ) -> ProviderResult:
        """Judge = simple message, no tools."""
        api_key = _get_api_key()
        if not api_key:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error="No ANTHROPIC_API_KEY set",
            )
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        return await self._run_simple(client, prompt, system_prompt, model, timeout_seconds)
