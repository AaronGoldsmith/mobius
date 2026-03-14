"""Main orchestration: task -> select -> swarm -> judge -> record -> return best."""

from __future__ import annotations

import logging

from mobius.config import MobiusConfig
from mobius.db import vec_to_blob
from mobius.embedder import embed
from mobius.judge import JudgePanel
from mobius.memory import Memory
from mobius.models import AgentRecord, JudgeVerdict, MatchRecord, MemoryEntry
from mobius.selector import Selector
from mobius.swarm import Swarm, SwarmResult
from mobius.tournament import Tournament
from mobius.ui import SwarmUI

logger = logging.getLogger(__name__)


class CompetitionResult:
    """Full result of a single competition."""

    def __init__(
        self,
        match: MatchRecord,
        verdict: JudgeVerdict | None,
        agents: dict[str, AgentRecord],
        swarm_result: SwarmResult,
        judge_models: list[str],
        strategy: str,
    ):
        self.match = match
        self.verdict = verdict
        self.agents = agents
        self.swarm_result = swarm_result
        self.judge_models = judge_models
        self.strategy = strategy

    @property
    def winner(self) -> AgentRecord | None:
        if self.verdict and self.verdict.winner:
            return self.agents.get(self.verdict.winner)
        return None

    @property
    def winning_output(self) -> str | None:
        if self.verdict and self.verdict.winner:
            result = self.swarm_result.successful_outputs.get(self.verdict.winner)
            return result.output if result else None
        return None


class Orchestrator:
    """Thin coordinator for the full competition flow."""

    def __init__(
        self,
        config: MobiusConfig,
        selector: Selector,
        swarm: Swarm,
        judge_panel: JudgePanel,
        tournament: Tournament,
        memory: Memory,
    ):
        self.config = config
        self.selector = selector
        self.swarm = swarm
        self.judge_panel = judge_panel
        self.tournament = tournament
        self.memory = memory

    async def run_competition(
        self,
        task: str,
        show_ui: bool = True,
    ) -> CompetitionResult:
        """Execute a full competition: select -> swarm -> judge -> record."""

        # 1. Select agents
        agents, strategy, memory_matches = self.selector.select(task)

        # 1b. If no strong contender, try to spawn a new agent on the fly
        if getattr(self.selector, "needs_new_agent", False):
            logger.info("Selector flagged: no strong contender. Attempting to create one.")
            try:
                from mobius.agent_builder import AgentBuilder
                builder = AgentBuilder(self.config)
                new_agent = await builder.create_agent(
                    specialization="auto",
                    description=f"Agent created on-the-fly for task: {task[:100]}",
                )
                if new_agent:
                    from mobius.registry import Registry
                    # Get registry from selector
                    registry = self.selector.registry
                    if not registry.get_agent_by_slug(new_agent.slug):
                        registry.create_agent(new_agent)
                        agents.append(new_agent)
                        logger.info("Created on-the-fly agent: %s", new_agent.slug)
            except Exception as e:
                logger.warning("Failed to create on-the-fly agent: %s", e)

        if not agents:
            match = MatchRecord(
                task_description=task,
                competitor_ids=[],
                voided=True,
            )
            return CompetitionResult(
                match=match,
                verdict=None,
                agents={},
                swarm_result=SwarmResult(outputs={}, task=task),
                judge_models=[],
                strategy=strategy,
            )

        agent_map = {a.id: a for a in agents}
        logger.info(
            "Selected %d agents (strategy=%s): %s",
            len(agents),
            strategy,
            [a.slug for a in agents],
        )

        # 2. Run swarm
        ui = SwarmUI() if show_ui else None
        if ui:
            # Register agents for UI display
            for a in agents:
                ui.agents[a.id] = a
                ui.statuses[a.id] = "waiting"

        live_ctx = ui.start() if ui else None
        try:
            if live_ctx:
                with live_ctx:
                    swarm_result = await self.swarm.run(
                        task=task,
                        agents=agents,
                        on_start=ui.on_start if ui else None,
                        on_complete=ui.on_complete if ui else None,
                    )
            else:
                swarm_result = await self.swarm.run(task=task, agents=agents)
        finally:
            if ui:
                ui.stop()

        # 3. Check if we have enough outputs to judge
        successful = swarm_result.successful_outputs
        if len(successful) == 0:
            logger.warning("All agents failed. Voiding match.")
            match = MatchRecord(
                task_description=task,
                competitor_ids=[a.id for a in agents],
                voided=True,
            )
            self.tournament.record_match(match)
            return CompetitionResult(
                match=match,
                verdict=None,
                agents=agent_map,
                swarm_result=swarm_result,
                judge_models=[],
                strategy=strategy,
            )

        if len(successful) == 1:
            # Single survivor wins by default
            winner_id = list(successful.keys())[0]
            verdict = JudgeVerdict(
                rankings=[],
                winner=winner_id,
                reasoning="Only one agent produced output — wins by default.",
                scores={winner_id: 30.0},
            )
            judge_models: list[str] = ["default-single-survivor"]
        else:
            # 4. Judge the outputs
            outputs_text = {
                aid: result.output for aid, result in successful.items()
            }
            verdict, judge_models = await self.judge_panel.evaluate(task, outputs_text)

        # 5. Record match
        task_vec = embed(task, self.config)
        match = MatchRecord(
            task_description=task,
            task_embedding=vec_to_blob(task_vec),
            competitor_ids=[a.id for a in agents],
            outputs={aid: r.output for aid, r in swarm_result.outputs.items() if r.success},
            judge_models=judge_models,
            judge_reasoning=verdict.reasoning if verdict else "",
            winner_id=verdict.winner if verdict else None,
            scores=verdict.scores if verdict else {},
            voided=verdict is None,
        )
        self.tournament.record_match(match)

        # 6. Store in memory
        if verdict and verdict.winner:
            memory_entry = MemoryEntry(
                task_embedding=vec_to_blob(task_vec),
                task_text=task,
                winning_agent_id=verdict.winner,
                score=max(verdict.scores.values()) if verdict.scores else 0.0,
            )
            self.memory.store(memory_entry)

        return CompetitionResult(
            match=match,
            verdict=verdict,
            agents=agent_map,
            swarm_result=swarm_result,
            judge_models=judge_models,
            strategy=strategy,
        )
