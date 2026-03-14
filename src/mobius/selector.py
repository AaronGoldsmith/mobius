"""Agent selection: pick N agents for a task using Elo, memory, and exploration."""

from __future__ import annotations

import logging
import random
from typing import Literal

from mobius.config import MobiusConfig
from mobius.memory import Memory, MemoryMatch
from mobius.models import AgentRecord
from mobius.registry import Registry

logger = logging.getLogger(__name__)

Strategy = Literal["diverse", "specialist", "ensemble"]


class Selector:
    """Picks agents for a competition based on task similarity and Elo."""

    def __init__(
        self, registry: Registry, memory: Memory, config: MobiusConfig
    ):
        self.registry = registry
        self.memory = memory
        self.config = config

    def determine_strategy(self, matches: list[MemoryMatch]) -> Strategy:
        """Choose selection strategy based on memory similarity."""
        if not matches:
            return "diverse"

        best_sim = matches[0].similarity
        if best_sim > self.config.similarity_specialist_threshold:
            return "specialist"
        elif best_sim > self.config.similarity_ensemble_threshold:
            return "ensemble"
        return "diverse"

    def select(
        self,
        task_text: str,
        n: int | None = None,
        force_strategy: Strategy | None = None,
    ) -> tuple[list[AgentRecord], Strategy, list[MemoryMatch]]:
        """Select N agents for a task.

        Returns (agents, strategy_used, memory_matches).
        """
        n = n or self.config.swarm_size
        all_agents = self.registry.list_agents()

        if len(all_agents) == 0:
            logger.warning("No agents in registry. Run 'mobius bootstrap' first.")
            return [], "diverse", []

        if len(all_agents) <= n:
            logger.info("Only %d agents available, using all", len(all_agents))
            return all_agents, "ensemble", []

        # Find similar past tasks
        memory_matches = self.memory.find_similar(task_text)
        strategy = force_strategy or self.determine_strategy(memory_matches)

        logger.info("Selection strategy: %s (best similarity: %.3f)",
                     strategy,
                     memory_matches[0].similarity if memory_matches else 0.0)

        match strategy:
            case "specialist":
                selected = self._select_specialist(all_agents, memory_matches, n)
            case "ensemble":
                selected = self._select_ensemble(all_agents, memory_matches, n)
            case "diverse":
                selected = self._select_diverse(all_agents, n)

        return selected, strategy, memory_matches

    def _select_specialist(
        self,
        agents: list[AgentRecord],
        matches: list[MemoryMatch],
        n: int,
    ) -> list[AgentRecord]:
        """Pick past winners + top Elo + 1 wildcard."""
        selected: list[AgentRecord] = []
        selected_ids: set[str] = set()

        # Past winners (up to n-2)
        for m in matches[:n - 2]:
            agent = self.registry.get_agent(m.entry.winning_agent_id)
            if agent and agent.id not in selected_ids:
                selected.append(agent)
                selected_ids.add(agent.id)

        # Top Elo to fill up to n-1
        for a in agents:
            if len(selected) >= n - 1:
                break
            if a.id not in selected_ids:
                selected.append(a)
                selected_ids.add(a.id)

        # 1 wildcard (low match count for exploration)
        wildcards = [a for a in agents if a.id not in selected_ids]
        wildcards.sort(key=lambda a: a.total_matches)
        if wildcards:
            selected.append(wildcards[0])

        return selected[:n]

    def _select_ensemble(
        self,
        agents: list[AgentRecord],
        matches: list[MemoryMatch],
        n: int,
    ) -> list[AgentRecord]:
        """Mix of memory winners + top Elo + wildcards."""
        selected: list[AgentRecord] = []
        selected_ids: set[str] = set()

        # Memory winners (up to 2)
        for m in matches[:2]:
            agent = self.registry.get_agent(m.entry.winning_agent_id)
            if agent and agent.id not in selected_ids:
                selected.append(agent)
                selected_ids.add(agent.id)

        # Top Elo (up to n-1)
        for a in agents:
            if len(selected) >= n - 1:
                break
            if a.id not in selected_ids:
                selected.append(a)
                selected_ids.add(a.id)

        # 1 wildcard
        wildcards = [a for a in agents if a.id not in selected_ids]
        wildcards.sort(key=lambda a: a.total_matches)
        if wildcards:
            selected.append(wildcards[0])

        return selected[:n]

    def _select_diverse(
        self, agents: list[AgentRecord], n: int
    ) -> list[AgentRecord]:
        """Maximize diversity of specializations and providers."""
        selected: list[AgentRecord] = []
        selected_ids: set[str] = set()
        seen_specs: set[str] = set()
        seen_providers: set[str] = set()

        # First pass: one agent per unique specialization
        for a in agents:
            if len(selected) >= n:
                break
            agent_specs = set(a.specializations)
            if not agent_specs & seen_specs or a.provider not in seen_providers:
                selected.append(a)
                selected_ids.add(a.id)
                seen_specs.update(agent_specs)
                seen_providers.add(a.provider)

        # Fill remaining slots randomly from unselected agents
        remaining = [a for a in agents if a.id not in selected_ids]
        random.shuffle(remaining)
        for a in remaining:
            if len(selected) >= n:
                break
            selected.append(a)

        return selected[:n]
