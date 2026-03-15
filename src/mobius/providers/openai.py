"""OpenAI provider with optional tool use."""

from __future__ import annotations

import asyncio
import json
import logging

from mobius.providers.base import Provider, ProviderResult
from mobius.providers.tools import OPENAI_BASH_TOOL, run_command

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
        """Execute via OpenAI chat completions, with tool loop if requested."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error="openai SDK not installed",
            )

        client = AsyncOpenAI()
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
        """Single-shot completion, no tools."""
        try:
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
                output=output, model=model, provider=self.name,
                tokens_in=tokens_in, tokens_out=tokens_out,
            )
        except asyncio.TimeoutError:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error=f"Timeout after {timeout_seconds}s", truncated=True,
            )
        except Exception as e:
            logger.error("OpenAI agent error: %s", e)
            return ProviderResult(
                output="", model=model, provider=self.name, error=str(e),
            )

    async def _run_with_tools(
        self, client, prompt: str, system_prompt: str,
        model: str, max_turns: int, timeout_seconds: int,
        working_dir: str | None = None,
    ) -> ProviderResult:
        """Agentic loop with function calling."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        total_in, total_out = 0, 0
        text_outputs: list[str] = []
        turn = 0

        try:
            for turn in range(max_turns):
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=[OPENAI_BASH_TOOL],
                        max_tokens=4096,
                    ),
                    timeout=timeout_seconds,
                )

                if response.usage:
                    total_in += response.usage.prompt_tokens
                    total_out += response.usage.completion_tokens

                choice = response.choices[0]
                message = choice.message

                # Capture any text content
                if message.content:
                    text_outputs.append(message.content)

                # If no tool calls, we're done
                if not message.tool_calls:
                    break

                # Append the assistant message (with tool_calls) to history
                messages.append(message)

                # Execute each tool call and add results
                for tool_call in message.tool_calls:
                    if tool_call.function.name == "bash":
                        args = json.loads(tool_call.function.arguments)
                        cmd = args.get("command", "")
                        logger.info("Agent running: %s", cmd[:100])
                        result = await asyncio.to_thread(
                            run_command, cmd, timeout=30,
                            working_dir=working_dir,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        })

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
            logger.error("OpenAI tools error: %s", e)
            return ProviderResult(
                output="\n".join(text_outputs), model=model, provider=self.name,
                error=str(e), tokens_in=total_in, tokens_out=total_out,
            )

    async def run_judge(
        self, prompt: str, system_prompt: str, model: str,
        max_budget_usd: float = 0.15, timeout_seconds: int = 120,
    ) -> ProviderResult:
        """Run judge evaluation via OpenAI — no tools."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error="openai SDK not installed",
            )
        client = AsyncOpenAI()
        return await self._run_simple(
            client, prompt, system_prompt, model, timeout_seconds,
        )
