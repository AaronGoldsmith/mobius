"""Pydantic models for all Mobius data records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid4().hex


ProviderType = Literal["anthropic", "google", "openai", "openrouter"]


class AgentRecord(BaseModel):
    """A single agent definition stored in the registry."""

    id: str = Field(default_factory=_uuid)
    name: str
    slug: str
    description: str
    system_prompt: str
    provider: ProviderType = "anthropic"
    model: str = "claude-haiku-4-5-20251001"
    tools: list[str] = Field(default_factory=lambda: ["Read", "Grep", "Glob"])
    max_turns: int = 10
    specializations: list[str] = Field(default_factory=list)
    generation: int = 1
    parent_id: str | None = None
    is_champion: bool = False
    elo_rating: float = 1500.0
    win_rate: float = 0.0
    total_matches: int = 0
    created_at: datetime = Field(default_factory=_now)


class TeamRecord(BaseModel):
    """A named group of agents that work together."""

    id: str = Field(default_factory=_uuid)
    name: str
    agent_ids: list[str]
    strategy: Literal["diverse", "specialist", "ensemble"] = "ensemble"
    specializations: list[str] = Field(default_factory=list)
    is_champion: bool = False
    generation: int = 1
    elo_rating: float = 1500.0


class MatchRecord(BaseModel):
    """A single competition between agents."""

    id: str = Field(default_factory=_uuid)
    task_description: str
    task_embedding: bytes | None = None
    competitor_ids: list[str]
    outputs: dict[str, str] = Field(default_factory=dict)
    judge_models: list[str] = Field(default_factory=list)
    judge_reasoning: str = ""
    winner_id: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    voided: bool = False
    created_at: datetime = Field(default_factory=_now)


class MemoryEntry(BaseModel):
    """Vector memory: maps task embeddings to winning agents."""

    id: str = Field(default_factory=_uuid)
    task_embedding: bytes
    task_text: str
    winning_agent_id: str
    winning_team_id: str | None = None
    score: float
    created_at: datetime = Field(default_factory=_now)


class CandidateRanking(BaseModel):
    """Score breakdown for a single candidate."""

    candidate: str
    correctness: float = 0
    quality: float = 0
    completeness: float = 0
    total: float = 0


class JudgeVerdict(BaseModel):
    """Structured output from a single judge evaluation."""

    rankings: list[CandidateRanking] = Field(default_factory=list)
    winner: str  # Candidate label (A, B, C, ...) or agent_id after consensus
    reasoning: str
    scores: dict[str, float] = Field(default_factory=dict)  # agent_id -> total score
