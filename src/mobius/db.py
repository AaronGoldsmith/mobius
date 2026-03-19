"""SQLite + sqlite-vec database setup, schema, and helpers."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import numpy as np

from mobius.config import MobiusConfig

logger = logging.getLogger(__name__)

# Schema version for future migrations
SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'anthropic',
    model TEXT NOT NULL,
    tools TEXT NOT NULL DEFAULT '[]',        -- JSON array
    max_turns INTEGER NOT NULL DEFAULT 10,
    specializations TEXT NOT NULL DEFAULT '[]', -- JSON array
    generation INTEGER NOT NULL DEFAULT 1,
    parent_id TEXT,
    is_champion INTEGER NOT NULL DEFAULT 0,
    elo_rating REAL NOT NULL DEFAULT 1500.0,
    win_rate REAL NOT NULL DEFAULT 0.0,
    total_matches INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_agents_slug ON agents(slug);
CREATE INDEX IF NOT EXISTS idx_agents_champion ON agents(is_champion, elo_rating DESC);
CREATE INDEX IF NOT EXISTS idx_agents_specialization ON agents(is_champion);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    agent_ids TEXT NOT NULL DEFAULT '[]',    -- JSON array
    strategy TEXT NOT NULL DEFAULT 'ensemble',
    specializations TEXT NOT NULL DEFAULT '[]',
    is_champion INTEGER NOT NULL DEFAULT 0,
    generation INTEGER NOT NULL DEFAULT 1,
    elo_rating REAL NOT NULL DEFAULT 1500.0
);

CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY,
    task_description TEXT NOT NULL,
    task_embedding BLOB,
    competitor_ids TEXT NOT NULL DEFAULT '[]',
    outputs TEXT NOT NULL DEFAULT '{}',       -- JSON dict
    judge_models TEXT NOT NULL DEFAULT '[]',
    judge_reasoning TEXT NOT NULL DEFAULT '',
    winner_id TEXT,
    scores TEXT NOT NULL DEFAULT '{}',        -- JSON dict
    voided INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_matches_created ON matches(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_matches_winner ON matches(winner_id);

CREATE TABLE IF NOT EXISTS memory (
    id TEXT PRIMARY KEY,
    task_text TEXT NOT NULL,
    winning_agent_id TEXT NOT NULL,
    winning_team_id TEXT,
    score REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""

# sqlite-vec virtual table created separately (requires extension)
VEC_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0(
    id TEXT PRIMARY KEY,
    task_embedding FLOAT[{dim}]
);
"""


def _load_sqlite_vec(conn: sqlite3.Connection) -> bool:
    """Try to load the sqlite-vec extension. Returns True if successful."""
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        logger.info("sqlite-vec extension loaded successfully")
        return True
    except (ImportError, Exception) as e:
        logger.warning("sqlite-vec not available: %s. Vector search disabled.", e)
        return False


def get_connection(config: MobiusConfig) -> sqlite3.Connection:
    """Get a configured SQLite connection."""
    config.data_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(config.db_path),
        timeout=10.0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    return conn


def init_db(config: MobiusConfig) -> tuple[sqlite3.Connection, bool]:
    """Initialize the database. Returns (connection, vec_available)."""
    conn = get_connection(config)

    # Load sqlite-vec before creating schema
    vec_available = _load_sqlite_vec(conn)

    # Create core schema
    conn.executescript(SCHEMA_SQL)

    # Create vector table if extension is available
    if vec_available:
        conn.execute(VEC_TABLE_SQL.format(dim=config.embedding_dim))

    # Track schema version
    existing = conn.execute("SELECT version FROM schema_version").fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )

    conn.commit()

    logger.info("Database initialized at %s (vec=%s)", config.db_path, vec_available)
    return conn, vec_available


# --- Row conversion helpers ---


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict, parsing JSON fields."""
    d = dict(row)
    for key in ("tools", "specializations", "agent_ids", "competitor_ids", "judge_models"):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    for key in ("outputs", "scores"):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    # Convert integer booleans
    for key in ("is_champion", "voided"):
        if key in d:
            d[key] = bool(d[key])
    return d


def dict_to_row(d: dict) -> dict:
    """Prepare a dict for SQLite insertion, serializing complex fields."""
    out = dict(d)
    for key in ("tools", "specializations", "agent_ids", "competitor_ids", "judge_models"):
        if key in out and isinstance(out[key], list):
            out[key] = json.dumps(out[key])
    for key in ("outputs", "scores"):
        if key in out and isinstance(out[key], dict):
            out[key] = json.dumps(out[key])
    # Convert booleans to integers
    for key in ("is_champion", "voided"):
        if key in out and isinstance(out[key], bool):
            out[key] = int(out[key])
    # Convert datetime to string
    if "created_at" in out and hasattr(out["created_at"], "isoformat"):
        out["created_at"] = out["created_at"].isoformat()
    return out


def vec_to_blob(vec: np.ndarray) -> bytes:
    """Convert numpy array to bytes for sqlite-vec storage."""
    return vec.astype(np.float32).tobytes()


def blob_to_vec(blob: bytes) -> np.ndarray:
    """Convert bytes from sqlite-vec back to numpy array."""
    return np.frombuffer(blob, dtype=np.float32)
