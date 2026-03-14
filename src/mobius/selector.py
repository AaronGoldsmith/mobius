"""Agent selection: pick the best N agents for a task using fitness scoring."""

from __future__ import annotations

import logging
import random
from typing import Literal

import numpy as np

from mobius.config import MobiusConfig
from mobius.embedder import embed
from mobius.memory import Memory, MemoryMatch
from mobius.models import AgentRecord
from mobius.registry import Registry

logger = logging.getLogger(__name__)

Strategy = Literal["diverse", "specialist", "ensemble"]

# Keywords that hint at specialization relevance
SPEC_KEYWORDS: dict[str, list[str]] = {
    "coding": ["write", "function", "class", "implement", "code", "algorithm", "python", "script", "program", "refactor", "debug"],
    "python": ["python", "def ", "import", "pip", "pytest"],
    "testing": ["test", "unit test", "pytest", "tdd", "coverage", "assert"],
    "frontend": ["html", "css", "landing page", "ui", "ux", "design", "website", "tailwind", "react", "component", "dashboard"],
    "design": ["design", "landing", "page", "layout", "responsive", "theme", "color"],
    "research": ["research", "find", "search", "recommend", "best", "compare", "analyze", "github", "projects", "repos"],
    "curation": ["curate", "rank", "filter", "surface", "recommend"],
    "analysis": ["analyze", "deep dive", "investigate", "evaluate", "assess"],
    "trends": ["trend", "emerging", "rising", "new", "future", "outlook"],
    "practical": ["practical", "usable", "install", "docs", "maintained"],
}


def _task_fitness(agent: AgentRecord, task_text: str) -> float:
    """Score how well an agent's specializations match the task.

    Returns 0.0-1.0 fitness score based on keyword matching between
    the agent's specializations and the task text.
    """
    task_lower = task_text.lower()
    score = 0.0
    max_possible = 0.0

    for spec in agent.specializations:
        keywords = SPEC_KEYWORDS.get(spec, [])
        if not keywords:
            # Unknown specialization — small base score for having any spec
            max_possible += 1.0
            score += 0.1
            continue

        max_possible += 1.0
        hits = sum(1 for kw in keywords if kw in task_lower)
        if hits > 0:
            score += min(hits / len(keywords) * 2, 1.0)  # Cap at 1.0 per spec

    if max_possible == 0:
        return 0.1  # No specializations at all — low fitness

    return score / max_possible


class Selector:
    """Picks the best agents for a task using fitness, Elo, memory, and exploration."""

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
        """Select the best N agents for a task.

        Uses a composite score:
        - Fitness: how relevant is this agent's specialization to the task?
        - Elo: how good is this agent overall?
        - Memory: has this agent won similar tasks before?
        - Exploration: agents with fewer matches get a bonus

        Returns (agents, strategy_used, memory_matches).
        """
        n = n or self.config.swarm_size
        all_agents = self.registry.list_agents()

        if len(all_agents) == 0:
            logger.warning("No agents in registry.")
            return [], "diverse", []

        if len(all_agents) <= n:
            return all_agents, "ensemble", []

        # Find similar past tasks
        memory_matches = self.memory.find_similar(task_text)
        strategy = force_strategy or self.determine_strategy(memory_matches)

        # Memory winner IDs for bonus scoring
        memory_winner_ids = {m.entry.winning_agent_id for m in memory_matches}

        # Score every agent
        scored: list[tuple[float, AgentRecord]] = []
        for agent in all_agents:
            fitness = _task_fitness(agent, task_text)
            elo_norm = (agent.elo_rating - 1400) / 200  # Normalize around 0-1
            memory_bonus = 0.3 if agent.id in memory_winner_ids else 0.0
            exploration_bonus = 0.2 if agent.total_matches < 3 else 0.0

            composite = (
                fitness * 0.5          # 50% — is this agent built for this task?
                + elo_norm * 0.2       # 20% — how good is it overall?
                + memory_bonus         # 30% bonus if it won a similar task
                + exploration_bonus    # 20% bonus for under-tested agents
            )

            scored.append((composite, agent))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Log the ranking
        logger.info("Agent fitness ranking for task:")
        for score, agent in scored[:10]:
            logger.info("  %.3f  %s (%s) specs=%s", score, agent.slug, agent.provider, agent.specializations)

        # Pick top N-1 by composite score + 1 wildcard
        selected = [agent for _, agent in scored[:n - 1]]
        selected_ids = {a.id for a in selected}

        # Wildcard slot: if no strong contender exists (best fitness < 0.3),
        # flag that a new agent should be created for this task type.
        # Otherwise, pick a random existing agent for diversity.
        best_fitness = scored[0][0] if scored else 0
        remaining = [agent for _, agent in scored if agent.id not in selected_ids]

        self.needs_new_agent = best_fitness < 0.3  # Flag for orchestrator

        if remaining:
            if best_fitness >= 0.3:
                # Strong contenders exist — pick a random remaining agent
                wildcard = random.choice(remaining)
            else:
                # No strong fit — pick the least-tested agent (exploration)
                remaining.sort(key=lambda a: a.total_matches)
                wildcard = remaining[0]
            selected.append(wildcard)
            logger.info("Wildcard: %s (%s) [random=%s]",
                        wildcard.slug, wildcard.provider, best_fitness >= 0.3)

        if self.needs_new_agent:
            logger.info("No strong contender (best_fitness=%.3f) — consider creating a new agent for this task type", best_fitness)

        return selected[:n], strategy, memory_matches
