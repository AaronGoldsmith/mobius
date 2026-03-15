"""Tests for skill scripts (record_verdict, load_match, create_agent)."""

import contextlib
import importlib.util
import json
import sqlite3
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from mobius.config import MobiusConfig
from mobius.db import SCHEMA_SQL, row_to_dict
from mobius.models import AgentRecord
from mobius.registry import Registry
from mobius.tournament import Tournament


class _UnclosableConn:
    """Wraps a sqlite3.Connection so close() is a no-op (keeps in-memory DB alive for assertions)."""

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass  # no-op

    def __getattr__(self, name):
        return getattr(self._conn, name)


_CONFIG = MobiusConfig(data_dir="/tmp/mobius_test")


def _run_script(name, path, conn, *, argv=None, call_main=None):
    """Load and execute a skill script with patched DB and config.

    Args:
        name: Module name for importlib.
        path: File path to the script.
        conn: sqlite3 connection (wrapped to prevent close).
        argv: sys.argv entries after the script name. If None, sys.argv is not patched.
        call_main: Callable receiving the loaded module, should call mod.main(...).
                   Defaults to ``lambda mod: mod.main()``.
    """
    if call_main is None:
        call_main = lambda mod: mod.main()
    wrapped = _UnclosableConn(conn)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    argv_ctx = (
        patch.object(sys, "argv", [f"{name}.py"] + argv)
        if argv is not None
        else contextlib.nullcontext()
    )
    with argv_ctx, \
         patch("mobius.config.get_config", return_value=_CONFIG), \
         patch("mobius.db.init_db", return_value=(wrapped, False)):
        spec.loader.exec_module(mod)
        captured = StringIO()
        with patch("sys.stdout", captured):
            call_main(mod)
    return captured.getvalue()


@pytest.fixture
def setup():
    """Create an in-memory DB with two agents and a pending match."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    registry = Registry(conn, _CONFIG)
    tournament = Tournament(conn, _CONFIG, registry)

    a1 = AgentRecord(
        name="Alpha", slug="alpha", description="First",
        system_prompt="You are alpha.", elo_rating=1500.0,
    )
    a2 = AgentRecord(
        name="Beta", slug="beta", description="Second",
        system_prompt="You are beta.", elo_rating=1500.0,
    )
    registry.create_agent(a1)
    registry.create_agent(a2)

    # Insert a pending match (no winner yet)
    from mobius.db import dict_to_row
    from mobius.models import MatchRecord

    match = MatchRecord(
        task_description="Write a sorting algorithm",
        competitor_ids=[a1.id, a2.id],
        outputs={a1.id: "def sort(x): ...", a2.id: "def sort(x): ..."},
    )
    row = dict_to_row(match.model_dump())
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO matches ({cols}) VALUES ({placeholders})", list(row.values()))
    conn.commit()

    return _CONFIG, conn, registry, tournament, a1, a2, match


# ---------------------------------------------------------------------------
# record_verdict tests
# ---------------------------------------------------------------------------

class TestRecordVerdict:
    def _run(self, conn, argv):
        return _run_script(
            "record_verdict",
            ".claude/skills/mobius-judge/scripts/record_verdict.py",
            conn, argv=argv,
        )

    def test_records_winner_and_updates_elo(self, setup):
        config, conn, registry, tournament, a1, a2, match = setup
        scores = json.dumps({a1.id: 28.5, a2.id: 22.0})
        output = self._run(conn, [a1.id, scores, "Alpha was better"])

        # Verify match was updated in DB
        row = conn.execute("SELECT * FROM matches WHERE id = ?", (match.id,)).fetchone()
        m = row_to_dict(row)
        assert m["winner_id"] == a1.id
        assert m["judge_reasoning"] == "Alpha was better"
        assert m["voided"] is False

        # Verify Elo changed
        winner = registry.get_agent(a1.id)
        loser = registry.get_agent(a2.id)
        assert winner.elo_rating > 1500.0
        assert loser.elo_rating < 1500.0

        # Verify output mentions verdict
        assert "Verdict recorded" in output

    def test_partial_id_matching(self, setup):
        config, conn, registry, tournament, a1, a2, match = setup
        partial = a1.id[:8]
        scores = json.dumps({a1.id: 25.0, a2.id: 20.0})
        output = self._run(conn, [partial, scores, "Partial match test"])

        row = conn.execute("SELECT * FROM matches WHERE id = ?", (match.id,)).fetchone()
        m = row_to_dict(row)
        assert m["winner_id"] == a1.id

    def test_invalid_winner_exits(self, setup):
        config, conn, registry, tournament, a1, a2, match = setup
        scores = json.dumps({"fake": 30.0})
        with pytest.raises(SystemExit) as exc_info:
            self._run(conn, ["nonexistent-id", scores, "Bad winner"])
        assert exc_info.value.code == 1

    def test_stats_updated(self, setup):
        config, conn, registry, tournament, a1, a2, match = setup
        scores = json.dumps({a1.id: 28.0, a2.id: 22.0})
        self._run(conn, [a1.id, scores, "Alpha wins"])

        winner = registry.get_agent(a1.id)
        loser = registry.get_agent(a2.id)
        assert winner.total_matches == 1
        assert winner.win_rate == 1.0
        assert loser.total_matches == 1
        assert loser.win_rate == 0.0

    def test_match_flag_selects_specific_match(self, setup):
        config, conn, registry, tournament, a1, a2, match = setup
        scores = json.dumps({a1.id: 25.0, a2.id: 20.0})
        partial_match_id = match.id[:8]
        output = self._run(
            conn,
            ["--match", partial_match_id, a1.id, scores, "Specific match"],
        )
        assert "Verdict recorded" in output

    def test_elo_display_in_output(self, setup):
        config, conn, registry, tournament, a1, a2, match = setup
        scores = json.dumps({a1.id: 28.0, a2.id: 22.0})
        output = self._run(conn, [a1.id, scores, "Alpha wins"])
        assert "Elo updates:" in output
        assert "Alpha" in output
        assert "Beta" in output


# ---------------------------------------------------------------------------
# load_match tests
# ---------------------------------------------------------------------------

class TestLoadMatch:
    def _run(self, conn, argv=None):
        match_id = argv[0] if argv else None
        return _run_script(
            "load_match",
            ".claude/skills/mobius-judge/scripts/load_match.py",
            conn, call_main=lambda mod: mod.main(match_id),
        )

    def test_loads_latest_match(self, setup):
        _, conn, _, _, a1, a2, match = setup
        output = self._run(conn)
        assert "MATCH:" in output
        assert "Write a sorting algorithm" in output
        assert "COMPETITORS: 2" in output

    def test_loads_by_partial_id(self, setup):
        _, conn, _, _, a1, a2, match = setup
        output = self._run(conn, [match.id[:8]])
        assert match.id in output

    def test_no_match_exits(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        with pytest.raises(SystemExit) as exc_info:
            self._run(conn)
        assert exc_info.value.code == 1

    def test_shows_agent_names(self, setup):
        _, conn, _, _, a1, a2, match = setup
        output = self._run(conn)
        assert "Alpha" in output
        assert "Beta" in output


# ---------------------------------------------------------------------------
# create_agent tests
# ---------------------------------------------------------------------------

class TestCreateAgent:
    def _run(self, conn, agent_json):
        return _run_script(
            "create_agent",
            ".claude/skills/mobius-seed/scripts/create_agent.py",
            conn, argv=[json.dumps(agent_json)],
        )

    def test_creates_agent(self, setup):
        _, conn, registry, _, _, _, _ = setup
        output = self._run(conn, {
            "name": "Gamma",
            "slug": "gamma",
            "description": "Third agent",
            "system_prompt": "You are gamma.",
            "provider": "google",
            "model": "gemini-2.5-flash",
        })
        assert "Created: Gamma" in output
        agent = registry.get_agent_by_slug("gamma")
        assert agent is not None
        assert agent.provider == "google"

    def test_duplicate_slug_skips(self, setup):
        _, conn, _, _, _, _, _ = setup
        output = self._run(conn, {
            "name": "Alpha Dup",
            "slug": "alpha",
            "description": "Duplicate",
            "system_prompt": "Dup.",
        })
        assert "already exists" in output

    def test_missing_fields_exits(self, setup):
        _, conn, _, _, _, _, _ = setup
        with pytest.raises(SystemExit) as exc_info:
            self._run(conn, {"name": "Incomplete"})
        assert exc_info.value.code == 1

    def test_default_provider_and_model(self, setup):
        _, conn, registry, _, _, _, _ = setup
        self._run(conn, {
            "name": "Delta",
            "slug": "delta",
            "description": "Defaults test",
            "system_prompt": "You are delta.",
        })
        agent = registry.get_agent_by_slug("delta")
        assert agent.provider == "anthropic"
        assert agent.model == "claude-haiku-4-5-20251001"
