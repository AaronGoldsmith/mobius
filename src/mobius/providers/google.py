"""Google Gemini provider with optional tool use."""

from __future__ import annotations

import asyncio
import logging
import os

from mobius.providers.base import Provider, ProviderResult
from mobius.providers.tools import GOOGLE_BASH_DECLARATION, run_command

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
        """Execute via Google GenAI SDK, with tool loop if requested."""
        api_key = _get_api_key()
        if not api_key:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error="No Google API key (set GOOGLE_API_KEY or GEMINI_API_KEY)",
            )

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error="google-genai not installed",
            )

        client = genai.Client(api_key=api_key)
        use_tools = tools and "Bash" in tools

        if use_tools:
            return await self._run_with_tools(
                client, types, prompt, system_prompt, model,
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
        """Single-shot generation, no tools."""
        try:
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
                output=output, model=model, provider=self.name,
                tokens_in=tokens_in, tokens_out=tokens_out,
            )
        except asyncio.TimeoutError:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error=f"Timeout after {timeout_seconds}s", truncated=True,
            )
        except Exception as e:
            logger.error("Google agent error: %s", e)
            return ProviderResult(
                output="", model=model, provider=self.name, error=str(e),
            )

    async def _run_with_tools(
        self, client, types, prompt: str, system_prompt: str,
        model: str, max_turns: int, timeout_seconds: int,
        working_dir: str | None = None,
    ) -> ProviderResult:
        """Agentic loop with function calling."""
        # Build the tool declaration
        bash_tool = types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=GOOGLE_BASH_DECLARATION["name"],
                description=GOOGLE_BASH_DECLARATION["description"],
                parameters=GOOGLE_BASH_DECLARATION["parameters"],
            ),
        ])

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[bash_tool],
            max_output_tokens=16384,
        )

        contents = [types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )]

        total_in, total_out = 0, 0
        text_outputs: list[str] = []
        turn = 0

        try:
            for turn in range(max_turns):
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=timeout_seconds,
                )

                total_in += getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                total_out += getattr(response.usage_metadata, "candidates_token_count", 0) or 0

                # Extract text and function calls from the response
                candidate = response.candidates[0]
                has_function_calls = False
                function_call_parts = []

                for part in candidate.content.parts:
                    if part.text:
                        text_outputs.append(part.text)
                    if part.function_call:
                        has_function_calls = True
                        function_call_parts.append(part)

                if not has_function_calls:
                    logger.debug(
                        "Tool loop ended: no function calls, turn=%d/%d",
                        turn + 1, max_turns,
                    )
                    break

                # Add model response to conversation
                contents.append(candidate.content)

                # Execute function calls and build response parts
                response_parts = []
                for part in function_call_parts:
                    fc = part.function_call
                    if fc.name == "bash":
                        cmd = fc.args.get("command", "")
                        logger.info("Agent running: %s", cmd[:100])
                        result = await asyncio.to_thread(
                            run_command, cmd, timeout=30,
                            working_dir=working_dir,
                        )
                        response_parts.append(
                            types.Part.from_function_response(
                                name="bash",
                                response={"output": result},
                            )
                        )

                contents.append(types.Content(
                    role="user",
                    parts=response_parts,
                ))

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
            logger.error("Google tools error: %s", e)
            return ProviderResult(
                output="\n".join(text_outputs), model=model, provider=self.name,
                error=str(e), tokens_in=total_in, tokens_out=total_out,
            )

    async def run_judge(
        self, prompt: str, system_prompt: str, model: str,
        max_budget_usd: float = 0.15, timeout_seconds: int = 120,
    ) -> ProviderResult:
        """Run judge evaluation via Gemini — no tools."""
        api_key = _get_api_key()
        if not api_key:
            return ProviderResult(
                output="", model=model, provider=self.name,
                error="No Google API key (set GOOGLE_API_KEY or GEMINI_API_KEY)",
            )
        from google import genai
        client = genai.Client(api_key=api_key)
        return await self._run_simple(client, prompt, system_prompt, model, timeout_seconds)
