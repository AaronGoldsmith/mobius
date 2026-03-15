"""Tests for the Elo tournament system."""

import sqlite3

import pytest

from mobius.config import MobiusConfig
from mobius.db import SCHEMA_SQL, init_db
from mobius.models import AgentRecord, MatchRecord
from mobius.registry import Registry
from mobius.tournament import Tournament

from tests.helpers import make_agent as _make_agent


@pytest.fixture
def setup():
    """Create an in-memory tournament setup."""
    config = MobiusConfig(data_dir="/tmp/mobius_test")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    registry = Registry(conn, config)
    tournament = Tournament(conn, config, registry)
    return config, conn, registry, tournament


class TestEloMath:
    def test_expected_score_equal_ratings(self, setup):
        _, _, _, tournament = setup
        assert abs(tournament.expected_score(1500, 1500) - 0.5) < 0.001

    def test_expected_score_higher_rating(self, setup):
        _, _, _, tournament = setup
        score = tournament.expected_score(1700, 1500)
        assert score > 0.5
        assert score < 1.0

    def test_expected_score_lower_rating(self, setup):
        _, _, _, tournament = setup
        score = tournament.expected_score(1300, 1500)
        assert score < 0.5
        assert score > 0.0

    def test_expected_scores_sum_to_one(self, setup):
        _, _, _, tournament = setup
        e1 = tournament.expected_score(1600, 1400)
        e2 = tournament.expected_score(1400, 1600)
        assert abs(e1 + e2 - 1.0) < 0.001

    def test_update_elo_win(self, setup):
        _, _, _, tournament = setup
        new = tournament.update_elo(1500, 0.5, 1.0)
        assert new > 1500

    def test_update_elo_loss(self, setup):
        _, _, _, tournament = setup
        new = tournament.update_elo(1500, 0.5, 0.0)
        assert new < 1500

    def test_update_elo_draw(self, setup):
        _, _, _, tournament = setup
        new = tournament.update_elo(1500, 0.5, 0.5)
        assert abs(new - 1500) < 0.001


class TestMatchRecording:
    def test_record_match_updates_winner_elo(self, setup):
        config, conn, registry, tournament = setup
        a1 = _make_agent("agent-1")
        a2 = _make_agent("agent-2")
        registry.create_agent(a1)
        registry.create_agent(a2)

        match = MatchRecord(
            task_description="test task",
            competitor_ids=[a1.id, a2.id],
            winner_id=a1.id,
            scores={a1.id: 25.0, a2.id: 15.0},
        )
        tournament.record_match(match)

        updated_a1 = registry.get_agent(a1.id)
        updated_a2 = registry.get_agent(a2.id)
        assert updated_a1.elo_rating > 1500
        assert updated_a2.elo_rating < 1500

    def test_record_voided_match_no_elo_change(self, setup):
        config, conn, registry, tournament = setup
        a1 = _make_agent("agent-1")
        registry.create_agent(a1)

        match = MatchRecord(
            task_description="test task",
            competitor_ids=[a1.id],
            voided=True,
        )
        tournament.record_match(match)

        updated = registry.get_agent(a1.id)
        assert updated.elo_rating == 1500.0

    def test_three_way_match(self, setup):
        config, conn, registry, tournament = setup
        agents = [_make_agent(f"agent-{i}") for i in range(3)]
        for a in agents:
            registry.create_agent(a)

        match = MatchRecord(
            task_description="test task",
            competitor_ids=[a.id for a in agents],
            winner_id=agents[0].id,
            scores={a.id: (30 - i * 5) for i, a in enumerate(agents)},
        )
        tournament.record_match(match)

        ratings = [registry.get_agent(a.id).elo_rating for a in agents]
        # Winner should have highest new rating
        assert ratings[0] > ratings[1]
        assert ratings[0] > ratings[2]

    def test_win_rate_tracking(self, setup):
        config, conn, registry, tournament = setup
        a1 = _make_agent("agent-1")
        a2 = _make_agent("agent-2")
        registry.create_agent(a1)
        registry.create_agent(a2)

        # a1 wins twice
        for _ in range(2):
            match = MatchRecord(
                task_description="test",
                competitor_ids=[a1.id, a2.id],
                winner_id=a1.id,
                scores={a1.id: 25.0, a2.id: 15.0},
            )
            tournament.record_match(match)

        updated = registry.get_agent(a1.id)
        assert updated.win_rate == 1.0
        assert updated.total_matches == 2


class TestLeaderboard:
    def test_leaderboard_ordering(self, setup):
        config, conn, registry, tournament = setup
        a1 = _make_agent("high-elo", elo=1700)
        a2 = _make_agent("low-elo", elo=1300)
        registry.create_agent(a1)
        registry.create_agent(a2)

        board = tournament.get_leaderboard()
        assert board[0]["slug"] == "high-elo"
        assert board[1]["slug"] == "low-elo"

    def test_empty_leaderboard(self, setup):
        _, _, _, tournament = setup
        board = tournament.get_leaderboard()
        assert board == []
