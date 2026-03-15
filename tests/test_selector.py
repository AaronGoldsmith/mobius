"""Tests for agent selection strategies."""

import sqlite3

import pytest

from mobius.config import MobiusConfig
from mobius.db import SCHEMA_SQL
from mobius.memory import Memory
from mobius.models import AgentRecord
from mobius.registry import Registry
from mobius.selector import Selector

from tests.helpers import make_agent as _make_agent


@pytest.fixture
def setup():
    config = MobiusConfig(data_dir="/tmp/mobius_test")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    registry = Registry(conn, config)
    memory = Memory(conn, config, vec_available=False)
    selector = Selector(registry, memory, config)
    return config, conn, registry, memory, selector


class TestStrategy:
    def test_no_matches_is_diverse(self, setup):
        *_, selector = setup
        assert selector.determine_strategy([]) == "diverse"

    def test_empty_registry_returns_empty(self, setup):
        *_, selector = setup
        agents, strategy, matches = selector.select("some task")
        assert agents == []
        assert strategy == "diverse"

    def test_fewer_agents_than_requested(self, setup):
        _, _, registry, _, selector = setup
        registry.create_agent(_make_agent("solo"))

        agents, strategy, _ = selector.select("task", n=5)
        assert len(agents) == 1

    def test_select_returns_n_agents(self, setup):
        _, _, registry, _, selector = setup
        for i in range(10):
            registry.create_agent(_make_agent(f"agent-{i}"))

        agents, _, _ = selector.select("task", n=5)
        assert len(agents) == 5

    def test_diverse_maximizes_variety(self, setup):
        _, _, registry, _, selector = setup
        registry.create_agent(_make_agent("py", specializations=["python"], provider="anthropic"))
        registry.create_agent(_make_agent("js", specializations=["javascript"], provider="google"))
        registry.create_agent(_make_agent("go", specializations=["golang"], provider="openai"))

        agents, _, _ = selector.select("task", n=3, force_strategy="diverse")
        providers = {a.provider for a in agents}
        # Should pick from different providers
        assert len(providers) >= 2
