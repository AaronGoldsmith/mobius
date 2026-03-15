"""Parallel agent execution via asyncio."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from mobius.config import MobiusConfig
from mobius.models import AgentRecord
from mobius.providers.base import ProviderResult
from mobius.runner import run_agent

logger = logging.getLogger(__name__)


@dataclass
class SwarmResult:
    """Results from running a swarm of agents on a task."""

    outputs: dict[str, ProviderResult]  # agent_id -> result
    task: str

    @property
    def successful_outputs(self) -> dict[str, ProviderResult]:
        """Only outputs where the agent succeeded."""
        return {k: v for k, v in self.outputs.items() if v.success}

    @property
    def success_count(self) -> int:
        return len(self.successful_outputs)


class Swarm:
    """Manages parallel agent execution with concurrency control."""

    def __init__(self, config: MobiusConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.swarm_concurrency)

    async def _run_one(
        self,
        agent: AgentRecord,
        task: str,
        working_dir: str | None = None,
        on_start: callable | None = None,
        on_complete: callable | None = None,
    ) -> tuple[str, ProviderResult]:
        """Run a single agent with semaphore control."""
        async with self.semaphore:
            if on_start:
                on_start(agent)

            result = await run_agent(
                agent=agent,
                task=task,
                working_dir=working_dir,
                timeout_seconds=self.config.agent_timeout_seconds,
                max_budget_usd=self.config.agent_budget_usd,
            )

            if on_complete:
                on_complete(agent, result)

            if result.success:
                logger.info("Agent %s completed successfully", agent.slug)
            else:
                logger.warning(
                    "Agent %s failed: %s", agent.slug, result.error or "empty output"
                )

            return agent.id, result

    async def run(
        self,
        task: str,
        agents: list[AgentRecord],
        working_dir: str | None = None,
        on_start: callable | None = None,
        on_complete: callable | None = None,
    ) -> SwarmResult:
        """Run all agents on the task concurrently."""
        working_dir = working_dir or os.getcwd()
        logger.info("Starting swarm with %d agents on task (cwd=%s)", len(agents), working_dir)

        tasks = [
            self._run_one(agent, task, working_dir, on_start, on_complete)
            for agent in agents
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        outputs: dict[str, ProviderResult] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("Swarm task exception: %s", result)
                continue
            agent_id, provider_result = result
            outputs[agent_id] = provider_result

        swarm_result = SwarmResult(outputs=outputs, task=task)
        logger.info(
            "Swarm complete: %d/%d succeeded",
            swarm_result.success_count,
            len(agents),
        )
        return swarm_result
