"""Shared test fixtures and helpers."""

from mobius.models import AgentRecord


def make_agent(slug: str, elo: float = 1500.0, **kwargs) -> AgentRecord:
    """Create an AgentRecord with sensible defaults for testing."""
    kwargs.setdefault("name", f"Test {slug}")
    kwargs.setdefault("description", "Test")
    kwargs.setdefault("system_prompt", "You are a test.")
    return AgentRecord(slug=slug, elo_rating=elo, **kwargs)
