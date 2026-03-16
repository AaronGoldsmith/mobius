"""Agent registry: CRUD, versioning, champion/challenger promotion, export."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from mobius.config import MobiusConfig
from mobius.db import dict_to_row, row_to_dict, vec_to_blob
from mobius.models import AgentRecord

logger = logging.getLogger(__name__)


class Registry:
    """Manages agent definitions in the database."""

    def __init__(self, conn: sqlite3.Connection, config: MobiusConfig, vec_available: bool = False):
        self.conn = conn
        self.config = config
        self.vec_available = vec_available

    def create_agent(self, agent: AgentRecord) -> AgentRecord:
        """Insert a new agent into the registry."""
        row = dict_to_row(agent.model_dump())
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        self.conn.execute(
            f"INSERT INTO agents ({cols}) VALUES ({placeholders})",
            list(row.values()),
        )

        # Embed description for semantic search
        if self.vec_available:
            self._embed_agent(agent)

        self.conn.commit()
        logger.info("Created agent: %s (%s)", agent.name, agent.slug)
        return agent

    def _embed_agent(self, agent: AgentRecord) -> None:
        """Embed an agent's description and store in agent_vec."""
        from mobius.embedder import embed

        text = f"{agent.name}: {agent.description}"
        vec = embed(text, self.config)
        self.conn.execute(
            "INSERT OR REPLACE INTO agent_vec (id, description_embedding) VALUES (?, ?)",
            (agent.id, vec_to_blob(vec)),
        )

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        """Fetch an agent by ID."""
        row = self.conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return None
        return AgentRecord(**row_to_dict(row))

    def get_agent_by_slug(self, slug: str) -> AgentRecord | None:
        """Fetch an agent by slug."""
        row = self.conn.execute(
            "SELECT * FROM agents WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return None
        return AgentRecord(**row_to_dict(row))

    def list_agents(
        self,
        specialization: str | None = None,
        champions_only: bool = False,
        provider: str | None = None,
    ) -> list[AgentRecord]:
        """List agents with optional filters."""
        query = "SELECT * FROM agents WHERE 1=1"
        params: list = []

        if champions_only:
            query += " AND is_champion = 1"
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        if specialization:
            query += " AND specializations LIKE ?"
            params.append(f'%"{specialization}"%')

        query += " ORDER BY elo_rating DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [AgentRecord(**row_to_dict(r)) for r in rows]

    def update_agent(self, agent_id: str, **fields) -> None:
        """Update specific fields on an agent."""
        if not fields:
            return
        row = dict_to_row(fields)
        set_clause = ", ".join(f"{k} = ?" for k in row.keys())
        self.conn.execute(
            f"UPDATE agents SET {set_clause} WHERE id = ?",
            [*row.values(), agent_id],
        )
        self.conn.commit()

    def update_stats(
        self, agent_id: str, won: bool, match_count_delta: int = 1
    ) -> None:
        """Update win rate and match count after a competition."""
        agent = self.get_agent(agent_id)
        if agent is None:
            return

        new_total = agent.total_matches + match_count_delta
        new_wins = (agent.win_rate * agent.total_matches) + (1 if won else 0)
        new_rate = new_wins / new_total if new_total > 0 else 0.0

        self.update_agent(
            agent_id,
            total_matches=new_total,
            win_rate=round(new_rate, 4),
        )

    def get_champions(self, specialization: str | None = None) -> list[AgentRecord]:
        """Get current champion agents."""
        return self.list_agents(specialization=specialization, champions_only=True)

    def promote_to_champion(self, agent_id: str) -> None:
        """Promote an agent to champion for its specializations.

        Demotes any existing champions with overlapping specializations.
        """
        agent = self.get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")

        # Demote overlapping champions
        for spec in agent.specializations:
            current_champions = self.get_champions(specialization=spec)
            for champ in current_champions:
                if champ.id != agent_id:
                    self.update_agent(champ.id, is_champion=False)
                    logger.info(
                        "Demoted champion %s (%s) for spec '%s'",
                        champ.name,
                        champ.slug,
                        spec,
                    )

        self.update_agent(agent_id, is_champion=True)
        logger.info("Promoted %s (%s) to champion", agent.name, agent.slug)

    def retire_agent(self, agent_id: str) -> None:
        """Remove an agent from the active pool (soft delete via low Elo)."""
        self.update_agent(agent_id, elo_rating=0.0, is_champion=False)
        logger.info("Retired agent %s", agent_id)

    def count_agents(self) -> int:
        """Total agent count."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM agents").fetchone()
        return row["cnt"]

    def export_to_claude_agents(self, agent: AgentRecord) -> Path:
        """Export an agent as a .claude/agents/ markdown file."""
        agents_dir = self.config.claude_agents_dir
        agents_dir.mkdir(parents=True, exist_ok=True)

        # Only export Anthropic agents (others don't work in Claude Code)
        if agent.provider != "anthropic":
            logger.warning(
                "Skipping export of non-Anthropic agent %s (%s)",
                agent.name,
                agent.provider,
            )
            return agents_dir

        filename = f"{agent.slug}.md"
        filepath = agents_dir / filename

        # Map model ID to alias if possible
        model_alias = agent.model
        if "haiku" in agent.model:
            model_alias = "haiku"
        elif "sonnet" in agent.model:
            model_alias = "sonnet"
        elif "opus" in agent.model:
            model_alias = "opus"

        tools_line = ", ".join(agent.tools) if agent.tools else ""

        content = f"""---
name: {agent.slug}
description: {agent.description}
model: {model_alias}
tools: {tools_line}
maxTurns: {agent.max_turns}
---

{agent.system_prompt}
"""
        filepath.write_text(content, encoding="utf-8")
        logger.info("Exported agent to %s", filepath)
        return filepath
