"""Tests for the agent registry."""

import sqlite3

import pytest

from mobius.config import MobiusConfig
from mobius.db import SCHEMA_SQL
from mobius.models import AgentRecord
from mobius.registry import Registry

from tests.helpers import make_agent as _make_agent


@pytest.fixture
def setup():
    config = MobiusConfig(data_dir="/tmp/mobius_test")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    registry = Registry(conn, config)
    return config, conn, registry


class TestCRUD:
    def test_create_and_get(self, setup):
        _, _, registry = setup
        agent = _make_agent("test-agent")
        registry.create_agent(agent)

        fetched = registry.get_agent(agent.id)
        assert fetched is not None
        assert fetched.slug == "test-agent"

    def test_get_by_slug(self, setup):
        _, _, registry = setup
        agent = _make_agent("my-slug")
        registry.create_agent(agent)

        fetched = registry.get_agent_by_slug("my-slug")
        assert fetched is not None
        assert fetched.id == agent.id

    def test_get_nonexistent(self, setup):
        _, _, registry = setup
        assert registry.get_agent("nonexistent") is None

    def test_list_agents(self, setup):
        _, _, registry = setup
        registry.create_agent(_make_agent("a"))
        registry.create_agent(_make_agent("b"))
        assert len(registry.list_agents()) == 2

    def test_list_by_provider(self, setup):
        _, _, registry = setup
        registry.create_agent(_make_agent("claude", provider="anthropic"))
        registry.create_agent(_make_agent("gemini", provider="google"))

        anthropic_agents = registry.list_agents(provider="anthropic")
        assert len(anthropic_agents) == 1
        assert anthropic_agents[0].slug == "claude"

    def test_update_agent(self, setup):
        _, _, registry = setup
        agent = _make_agent("test")
        registry.create_agent(agent)

        registry.update_agent(agent.id, elo_rating=1600.0)
        updated = registry.get_agent(agent.id)
        assert updated.elo_rating == 1600.0

    def test_duplicate_slug_raises(self, setup):
        _, _, registry = setup
        registry.create_agent(_make_agent("dup"))
        with pytest.raises(Exception):
            registry.create_agent(_make_agent("dup"))


class TestChampionPromotion:
    def test_promote_to_champion(self, setup):
        _, _, registry = setup
        agent = _make_agent("test", specializations=["coding"])
        registry.create_agent(agent)

        registry.promote_to_champion(agent.id)
        updated = registry.get_agent(agent.id)
        assert updated.is_champion is True

    def test_promotion_demotes_existing(self, setup):
        _, _, registry = setup
        old_champ = _make_agent("old", specializations=["coding"], is_champion=True)
        new_champ = _make_agent("new", specializations=["coding"])
        registry.create_agent(old_champ)
        registry.create_agent(new_champ)

        registry.promote_to_champion(new_champ.id)

        assert registry.get_agent(old_champ.id).is_champion is False
        assert registry.get_agent(new_champ.id).is_champion is True

    def test_get_champions(self, setup):
        _, _, registry = setup
        champ = _make_agent("champ", is_champion=True, specializations=["coding"])
        non_champ = _make_agent("nope", is_champion=False)
        registry.create_agent(champ)
        registry.create_agent(non_champ)

        champions = registry.get_champions()
        assert len(champions) == 1
        assert champions[0].slug == "champ"


class TestStats:
    def test_update_stats_win(self, setup):
        _, _, registry = setup
        agent = _make_agent("test")
        registry.create_agent(agent)

        registry.update_stats(agent.id, won=True)
        updated = registry.get_agent(agent.id)
        assert updated.total_matches == 1
        assert updated.win_rate == 1.0

    def test_update_stats_loss(self, setup):
        _, _, registry = setup
        agent = _make_agent("test")
        registry.create_agent(agent)

        registry.update_stats(agent.id, won=False)
        updated = registry.get_agent(agent.id)
        assert updated.total_matches == 1
        assert updated.win_rate == 0.0

    def test_count_agents(self, setup):
        _, _, registry = setup
        assert registry.count_agents() == 0
        registry.create_agent(_make_agent("a"))
        assert registry.count_agents() == 1
