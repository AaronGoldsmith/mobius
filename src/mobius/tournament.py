"""Elo rating system and match recording."""

from __future__ import annotations

import logging
import sqlite3
from itertools import combinations

from mobius.config import MobiusConfig
from mobius.db import dict_to_row, row_to_dict
from mobius.models import MatchRecord
from mobius.registry import Registry

logger = logging.getLogger(__name__)


class Tournament:
    """Tracks agent performance via Elo ratings."""

    def __init__(self, conn: sqlite3.Connection, config: MobiusConfig, registry: Registry):
        self.conn = conn
        self.config = config
        self.registry = registry

    def expected_score(self, rating_a: float, rating_b: float) -> float:
        """Expected score for player A against player B."""
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def update_elo(self, rating: float, expected: float, actual: float) -> float:
        """Calculate new Elo rating."""
        return rating + self.config.elo_k_factor * (actual - expected)

    def record_match(self, match: MatchRecord) -> MatchRecord:
        """Record a match and update Elo ratings for all participants.

        Uses pairwise Elo updates: each pair of competitors within the match
        is treated as a separate contest. Winner gets actual=1 against all losers,
        losers get actual=0 against winner, and actual=0.5 against each other.
        """
        row = dict_to_row(match.model_dump())
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        self.conn.execute(
            f"INSERT INTO matches ({cols}) VALUES ({placeholders})",
            list(row.values()),
        )

        if match.voided or match.winner_id is None:
            self.conn.commit()
            logger.info("Match %s voided, no Elo update", match.id)
            return match

        # Collect current ratings
        ratings: dict[str, float] = {}
        for cid in match.competitor_ids:
            agent = self.registry.get_agent(cid)
            if agent:
                ratings[cid] = agent.elo_rating

        # Pairwise Elo updates
        new_ratings: dict[str, float] = dict(ratings)
        for a_id, b_id in combinations(match.competitor_ids, 2):
            if a_id not in ratings or b_id not in ratings:
                continue

            exp_a = self.expected_score(ratings[a_id], ratings[b_id])
            exp_b = 1.0 - exp_a

            if a_id == match.winner_id:
                actual_a, actual_b = 1.0, 0.0
            elif b_id == match.winner_id:
                actual_a, actual_b = 0.0, 1.0
            else:
                # Neither is winner — both lost, treat as draw between losers
                actual_a, actual_b = 0.5, 0.5

            new_ratings[a_id] = self.update_elo(new_ratings[a_id], exp_a, actual_a)
            new_ratings[b_id] = self.update_elo(new_ratings[b_id], exp_b, actual_b)

        # Write new ratings and update stats
        for cid, new_rating in new_ratings.items():
            self.registry.update_agent(cid, elo_rating=round(new_rating, 2))
            self.registry.update_stats(cid, won=(cid == match.winner_id))

        self.conn.commit()
        logger.info(
            "Match %s recorded. Winner: %s. Elo updates: %s",
            match.id,
            match.winner_id,
            {k: f"{ratings.get(k, 0):.0f}→{v:.0f}" for k, v in new_ratings.items()},
        )
        return match

    def get_leaderboard(
        self, specialization: str | None = None, limit: int = 20
    ) -> list[dict]:
        """Get ranked agents by Elo."""
        agents = self.registry.list_agents(specialization=specialization)
        return [
            {
                "rank": i + 1,
                "name": a.name,
                "slug": a.slug,
                "provider": a.provider,
                "model": a.model,
                "elo": a.elo_rating,
                "win_rate": a.win_rate,
                "matches": a.total_matches,
                "champion": a.is_champion,
                "specializations": a.specializations,
            }
            for i, a in enumerate(agents[:limit])
        ]

    def get_recent_matches(self, limit: int = 10) -> list[MatchRecord]:
        """Get most recent matches."""
        rows = self.conn.execute(
            "SELECT * FROM matches ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [MatchRecord(**row_to_dict(r)) for r in rows]

    def get_agent_matches(self, agent_id: str, limit: int = 20) -> list[MatchRecord]:
        """Get recent matches for a specific agent."""
        rows = self.conn.execute(
            "SELECT * FROM matches WHERE competitor_ids LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f'%"{agent_id}"%', limit),
        ).fetchall()
        return [MatchRecord(**row_to_dict(r)) for r in rows]

    def get_agent_recent_win_rate(self, agent_id: str, window: int = 20) -> float:
        """Win rate over the last N matches for an agent."""
        matches = self.get_agent_matches(agent_id, limit=window)
        if not matches:
            return 0.0
        wins = sum(1 for m in matches if m.winner_id == agent_id)
        return wins / len(matches)

    def total_matches(self) -> int:
        """Total match count."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM matches").fetchone()
        return row["cnt"]
