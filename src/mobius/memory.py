"""Vector memory: maps task embeddings to winning agents via sqlite-vec."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

import numpy as np

from mobius.config import MobiusConfig
from mobius.db import dict_to_row, row_to_dict, vec_to_blob
from mobius.embedder import embed
from mobius.models import MemoryEntry

logger = logging.getLogger(__name__)


@dataclass
class MemoryMatch:
    """A similar past task found in memory."""

    entry: MemoryEntry
    similarity: float


class Memory:
    """Vector store for task→winning agent mappings."""

    def __init__(
        self, conn: sqlite3.Connection, config: MobiusConfig, vec_available: bool
    ):
        self.conn = conn
        self.config = config
        self.vec_available = vec_available

    def store(self, entry: MemoryEntry) -> None:
        """Store a task outcome in memory."""
        row = dict_to_row(entry.model_dump(exclude={"task_embedding"}))
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        self.conn.execute(
            f"INSERT INTO memory ({cols}) VALUES ({placeholders})",
            list(row.values()),
        )

        # Store vector in the vec table if available
        if self.vec_available and entry.task_embedding:
            self.conn.execute(
                "INSERT INTO memory_vec (id, task_embedding) VALUES (?, ?)",
                (entry.id, entry.task_embedding),
            )

        self.conn.commit()
        logger.info("Stored memory entry %s for agent %s", entry.id, entry.winning_agent_id)

    def find_similar(self, task_text: str, top_k: int | None = None) -> list[MemoryMatch]:
        """Find similar past tasks using vector search."""
        if not self.vec_available:
            logger.warning("Vector search unavailable, returning empty results")
            return []

        top_k = top_k or self.config.memory_top_k
        task_vec = embed(task_text, self.config)
        task_blob = vec_to_blob(task_vec)

        rows = self.conn.execute(
            """
            SELECT m.*, mv.distance
            FROM memory_vec mv
            JOIN memory m ON m.id = mv.id
            WHERE mv.task_embedding MATCH ?
            ORDER BY mv.distance
            LIMIT ?
            """,
            (task_blob, top_k),
        ).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            distance = d.pop("distance")
            # sqlite-vec returns L2 distance; convert to cosine similarity
            # For normalized vectors, cosine_similarity = 1 - (L2_distance² / 2)
            similarity = 1.0 - (distance**2 / 2.0)
            entry = MemoryEntry(
                id=d["id"],
                task_embedding=b"",  # Don't load the full embedding
                task_text=d["task_text"],
                winning_agent_id=d["winning_agent_id"],
                winning_team_id=d.get("winning_team_id"),
                score=d["score"],
            )
            results.append(MemoryMatch(entry=entry, similarity=similarity))

        return results

    def count(self) -> int:
        """Total entries in memory."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM memory").fetchone()
        return row["cnt"]
