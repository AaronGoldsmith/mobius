"""Meta agent builder: creates, refines, and crossbreeds agent definitions via Opus."""

from __future__ import annotations

import json
import logging

from mobius.config import MobiusConfig
from mobius.models import AgentRecord, ProviderType
from mobius.runner import run_judge  # Reuse judge runner for Opus calls

logger = logging.getLogger(__name__)

BUILDER_SYSTEM_PROMPT = """You are an expert AI agent architect. Your job is to create high-quality agent definitions.

When creating an agent, you must return valid JSON in exactly this format:
{
    "name": "Human-readable agent name",
    "slug": "kebab-case-unique-slug",
    "description": "When this agent should be used (1 sentence)",
    "system_prompt": "The full system prompt for the agent. Be specific, detailed, and opinionated. Include: role definition, approach methodology, quality criteria, and output format expectations.",
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "tools": ["Read", "Grep", "Glob", "Bash", "Write", "Edit"],
    "specializations": ["coding", "refactoring"]
}

Guidelines for great agent prompts:
- Be specific about the agent's approach and methodology
- Include quality criteria the agent should self-check against
- Define output format expectations
- Include edge case handling instructions
- Keep prompts under 2000 tokens but detailed enough to guide behavior
- Match tools to the task: coding agents need Bash/Write/Edit; analysis agents need Read/Grep/Glob

Available providers and models:
- anthropic: claude-haiku-4-5-20251001 (fast/cheap), claude-sonnet-4-6 (balanced), claude-opus-4-6 (best)
- google: gemini-2.5-flash (fast/cheap), gemini-2.5-pro (balanced)
- openai: gpt-4o-mini (fast/cheap), gpt-4o (balanced)

Available tools (Anthropic only): Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
Non-Anthropic agents don't have tool access — their prompts should focus on generating complete outputs directly.

Do NOT output anything other than the JSON object."""

REFINE_PROMPT_TEMPLATE = """An agent needs improvement based on judge feedback.

## Current Agent
Name: {name}
Slug: {slug}
Provider: {provider}
Model: {model}
Current system prompt:
```
{system_prompt}
```

## Judge Feedback (from losses)
{feedback}

## Task
Create an improved version of this agent. Keep the same specializations but improve the system prompt to address the judge's criticism. Return the full agent JSON with the improved prompt.

Important: Use the same slug with a "-v{generation}" suffix (e.g., "{slug}-v{generation}"). Keep the same provider and model unless there's a strong reason to change."""

CROSSBREED_PROMPT_TEMPLATE = """Create a new agent by combining the strengths of two high-performing agents.

## Agent A (Elo: {elo_a})
Name: {name_a}
Specializations: {specs_a}
System prompt:
```
{prompt_a}
```

## Agent B (Elo: {elo_b})
Name: {name_b}
Specializations: {specs_b}
System prompt:
```
{prompt_b}
```

## Task
Create a new agent that combines the best strategies from both agents. The new agent should have a unique name/slug and merged specializations. Return the full agent JSON."""

SCOUT_PROMPT_TEMPLATE = """Analyze this codebase summary and create specialized agents for it.

## Codebase Summary
{summary}

## Task
Based on the codebase structure, identify the top {count} most valuable agent specializations and create agent definitions for each. Consider:
- The primary language(s) and frameworks used
- Common task patterns (testing, refactoring, debugging, documentation)
- Domain-specific needs

Return a JSON array of agent definitions:
[
    {{agent1}},
    {{agent2}},
    ...
]"""

BOOTSTRAP_SPECIALIZATIONS = [
    ("coding-general", "General-purpose coding assistant for writing new functions and features"),
    ("code-reviewer", "Expert code reviewer focused on quality, security, and best practices"),
    ("refactorer", "Specialist in refactoring code for clarity, performance, and maintainability"),
    ("debugger", "Expert debugger that traces issues, identifies root causes, and proposes fixes"),
    ("test-writer", "Specialist in writing comprehensive unit and integration tests"),
    ("api-designer", "Expert in designing clean, consistent, and well-documented APIs"),
    ("data-analyst", "Specialist in data analysis, transformation, and pipeline code"),
    ("doc-writer", "Technical writer that creates clear documentation and code comments"),
    ("optimizer", "Performance optimization specialist focused on speed and resource usage"),
    ("security-auditor", "Security specialist that identifies vulnerabilities and proposes fixes"),
]


def _parse_agent_json(raw: str) -> dict | list | None:
    """Extract agent JSON (object or array) from potentially noisy LLM output.

    Tries multiple strategies in order of preference:
    1. Strip markdown fences and parse directly
    2. Find JSON array first (for scout — returns multiple agents)
    3. Find individual JSON objects (for single agent creation)
    4. Find ALL JSON objects individually (fallback for when array parsing fails
       because the LLM put text between objects)
    """
    text = raw.strip()

    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        # Try each fenced block
        for part in parts[1::2]:  # odd-indexed parts are inside fences
            content = part.strip()
            if content.startswith("json"):
                content = content[4:].strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                continue

    # Try direct parse of full text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding JSON array FIRST (important for scout — array before object)
    arr_start = text.find("[")
    arr_end = text.rfind("]") + 1
    if arr_start >= 0 and arr_end > arr_start:
        try:
            parsed = json.loads(text[arr_start:arr_end])
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except json.JSONDecodeError:
            pass

    # Try finding a single JSON object
    obj_start = text.find("{")
    obj_end = text.rfind("}") + 1
    if obj_start >= 0 and obj_end > obj_start:
        try:
            return json.loads(text[obj_start:obj_end])
        except json.JSONDecodeError:
            pass

    # Fallback: find ALL individual JSON objects by brace-matching
    # This handles cases where the LLM puts explanatory text between objects
    objects = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:i + 1])
                    if "system_prompt" in obj or "slug" in obj:
                        objects.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None

    if objects:
        logger.info("Extracted %d agent definitions via brace-matching fallback", len(objects))
        return objects if len(objects) > 1 else objects[0]

    logger.error("Could not parse any JSON from LLM output (%d chars)", len(raw))
    return None


class AgentBuilder:
    """Meta agent that creates and improves agent definitions."""

    def __init__(self, config: MobiusConfig):
        self.config = config
        # Use the first Anthropic judge model for building, or fallback
        self.builder_provider: ProviderType = "anthropic"
        self.builder_model = "claude-opus-4-6"

    async def create_agent(
        self,
        specialization: str,
        description: str,
        provider: ProviderType = "anthropic",
        model: str | None = None,
    ) -> AgentRecord | None:
        """Create a new agent definition via the builder model."""
        prompt = f"""Create a specialized agent for: {specialization}

Description: {description}

The agent should use provider "{provider}" and model "{model or 'use your best judgment for the provider'}".

Focus on making the system prompt detailed, specific, and effective for this specialization."""

        result = await run_judge(
            prompt=prompt,
            system_prompt=BUILDER_SYSTEM_PROMPT,
            provider_name=self.builder_provider,
            model=self.builder_model,
        )

        if not result.success:
            logger.error("Agent builder failed: %s", result.error)
            return None

        data = _parse_agent_json(result.output)
        if data is None:
            logger.error("Could not parse agent builder output")
            return None

        try:
            return AgentRecord(
                name=data["name"],
                slug=data["slug"],
                description=data["description"],
                system_prompt=data["system_prompt"],
                provider=data.get("provider", provider),
                model=data.get("model", model or "claude-haiku-4-5-20251001"),
                tools=data.get("tools", ["Read", "Grep", "Glob"]),
                specializations=data.get("specializations", [specialization]),
            )
        except Exception as e:
            logger.error("Invalid agent definition from builder: %s", e)
            return None

    async def refine_agent(
        self,
        agent: AgentRecord,
        feedback: str,
    ) -> AgentRecord | None:
        """Create an improved version of an agent based on judge feedback."""
        prompt = REFINE_PROMPT_TEMPLATE.format(
            name=agent.name,
            slug=agent.slug,
            provider=agent.provider,
            model=agent.model,
            system_prompt=agent.system_prompt,
            feedback=feedback,
            generation=agent.generation + 1,
        )

        result = await run_judge(
            prompt=prompt,
            system_prompt=BUILDER_SYSTEM_PROMPT,
            provider_name=self.builder_provider,
            model=self.builder_model,
        )

        if not result.success:
            logger.error("Agent refinement failed: %s", result.error)
            return None

        data = _parse_agent_json(result.output)
        if data is None:
            return None

        try:
            return AgentRecord(
                name=data.get("name", agent.name),
                slug=data.get("slug", f"{agent.slug}-v{agent.generation + 1}"),
                description=data.get("description", agent.description),
                system_prompt=data["system_prompt"],
                provider=data.get("provider", agent.provider),
                model=data.get("model", agent.model),
                tools=data.get("tools", agent.tools),
                specializations=data.get("specializations", agent.specializations),
                generation=agent.generation + 1,
                parent_id=agent.id,
            )
        except Exception as e:
            logger.error("Invalid refined agent from builder: %s", e)
            return None

    async def crossbreed(
        self, agent_a: AgentRecord, agent_b: AgentRecord
    ) -> AgentRecord | None:
        """Create a new agent combining strengths of two agents."""
        prompt = CROSSBREED_PROMPT_TEMPLATE.format(
            elo_a=agent_a.elo_rating,
            name_a=agent_a.name,
            specs_a=", ".join(agent_a.specializations),
            prompt_a=agent_a.system_prompt,
            elo_b=agent_b.elo_rating,
            name_b=agent_b.name,
            specs_b=", ".join(agent_b.specializations),
            prompt_b=agent_b.system_prompt,
        )

        result = await run_judge(
            prompt=prompt,
            system_prompt=BUILDER_SYSTEM_PROMPT,
            provider_name=self.builder_provider,
            model=self.builder_model,
        )

        if not result.success:
            return None

        data = _parse_agent_json(result.output)
        if data is None:
            return None

        try:
            combined_specs = list(
                set(agent_a.specializations + agent_b.specializations)
            )
            return AgentRecord(
                name=data.get("name", f"{agent_a.name} x {agent_b.name}"),
                slug=data.get("slug", f"{agent_a.slug}-x-{agent_b.slug}"),
                description=data.get("description", "Crossbred agent"),
                system_prompt=data["system_prompt"],
                provider=data.get("provider", agent_a.provider),
                model=data.get("model", agent_a.model),
                tools=data.get("tools", agent_a.tools),
                specializations=data.get("specializations", combined_specs),
                parent_id=agent_a.id,
            )
        except Exception as e:
            logger.error("Invalid crossbred agent: %s", e)
            return None

    async def bootstrap(
        self,
    ) -> list[AgentRecord]:
        """Create initial set of agents across core specializations."""
        agents = []
        for spec, desc in BOOTSTRAP_SPECIALIZATIONS:
            logger.info("Bootstrapping agent for: %s", spec)
            agent = await self.create_agent(specialization=spec, description=desc)
            if agent:
                agents.append(agent)
                logger.info("Created: %s (%s)", agent.name, agent.slug)
            else:
                logger.warning("Failed to create agent for: %s", spec)
        return agents

    async def scout(self, codebase_summary: str, count: int = 5) -> list[AgentRecord]:
        """Analyze a codebase and generate specialized agents."""
        prompt = SCOUT_PROMPT_TEMPLATE.format(
            summary=codebase_summary, count=count
        )

        result = await run_judge(
            prompt=prompt,
            system_prompt=BUILDER_SYSTEM_PROMPT,
            provider_name=self.builder_provider,
            model=self.builder_model,
        )

        if not result.success:
            logger.error("Scout failed: %s", result.error)
            return []

        logger.info("Scout received %d chars from builder model", len(result.output))

        data = _parse_agent_json(result.output)
        if data is None:
            logger.error(
                "Scout could not parse any agents from output. First 500 chars: %s",
                result.output[:500],
            )
            return []

        # Handle both single object and array responses
        items = data if isinstance(data, list) else [data]
        logger.info("Scout parsed %d/%d requested agent definitions", len(items), count)

        agents = []
        for i, item in enumerate(items):
            try:
                agent = AgentRecord(
                    name=item["name"],
                    slug=item["slug"],
                    description=item["description"],
                    system_prompt=item["system_prompt"],
                    provider=item.get("provider", "anthropic"),
                    model=item.get("model", "claude-haiku-4-5-20251001"),
                    tools=item.get("tools", ["Read", "Grep", "Glob"]),
                    specializations=item.get("specializations", []),
                )
                agents.append(agent)
                logger.info("  [%d/%d] %s (%s) specs=%s", i + 1, len(items), agent.name, agent.provider, agent.specializations)
            except KeyError as e:
                logger.warning("  [%d/%d] Missing required field %s in: %s", i + 1, len(items), e, list(item.keys()))
            except Exception as e:
                logger.warning("  [%d/%d] Invalid agent definition: %s", i + 1, len(items), e)

        if len(agents) < count:
            logger.warning(
                "Scout created %d agents but %d were requested. %d failed to parse.",
                len(agents), count, count - len(agents),
            )

        return agents
