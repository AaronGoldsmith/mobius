"""Record a judge verdict for a match and update Elo ratings.

Usage:
    python record_verdict.py <winner_agent_id> <scores_json> <reasoning>
    python record_verdict.py --match <match_id> <winner_agent_id> <scores_json> <reasoning>

Example:
    python record_verdict.py abc123 '{"abc123": 28.5, "def456": 22.0}' "Agent A was more thorough..."
"""

import json
import sys

sys.path.insert(0, "src")

from mobius.config import get_config
from mobius.db import init_db, row_to_dict
from mobius.models import MatchRecord
from mobius.registry import Registry
from mobius.tournament import Tournament


def main():
    args = sys.argv[1:]

    # Parse optional --match flag
    match_id = None
    if "--match" in args:
        idx = args.index("--match")
        match_id = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if len(args) < 3:
        print("Usage: python record_verdict.py [--match <id>] <winner_id> <scores_json> <reasoning>")
        sys.exit(1)

    winner_id = args[0]
    scores = json.loads(args[1])
    reasoning = args[2]

    config = get_config()
    conn, _ = init_db(config)
    registry = Registry(conn, config)
    tournament = Tournament(conn, config, registry)

    # Get the match
    if match_id:
        row = conn.execute("SELECT * FROM matches WHERE id LIKE ?", (f"{match_id}%",)).fetchone()
    else:
        row = conn.execute("SELECT * FROM matches ORDER BY created_at DESC LIMIT 1").fetchone()

    if not row:
        print("No match found.")
        sys.exit(1)

    match = row_to_dict(row)
    mid = match["id"]

    # Validate winner is a competitor
    competitor_ids = match.get("competitor_ids", [])
    if isinstance(competitor_ids, str):
        competitor_ids = json.loads(competitor_ids)

    # Allow partial ID matching
    full_winner_id = None
    for cid in competitor_ids:
        if cid.startswith(winner_id) or cid == winner_id:
            full_winner_id = cid
            break

    if not full_winner_id:
        print(f"Winner '{winner_id}' not found in competitors: {[c[:8] for c in competitor_ids]}")
        sys.exit(1)

    # Update the match record
    conn.execute(
        """UPDATE matches SET
            winner_id = ?,
            scores = ?,
            judge_reasoning = ?,
            judge_models = ?,
            voided = 0
        WHERE id = ?""",
        (
            full_winner_id,
            json.dumps(scores),
            reasoning,
            json.dumps(["local-opus-judge"]),
            mid,
        ),
    )
    conn.commit()

    # Now re-read and update Elo via the tournament system
    updated_row = conn.execute("SELECT * FROM matches WHERE id = ?", (mid,)).fetchone()
    updated_match = MatchRecord(**row_to_dict(updated_row))

    # Collect old ratings for display
    old_ratings = {}
    for cid in updated_match.competitor_ids:
        agent = registry.get_agent(cid)
        if agent:
            old_ratings[cid] = agent.elo_rating

    # Update Elo ratings pairwise
    from itertools import combinations
    new_ratings = dict(old_ratings)
    for a_id, b_id in combinations(updated_match.competitor_ids, 2):
        if a_id not in old_ratings or b_id not in old_ratings:
            continue
        exp_a = tournament.expected_score(old_ratings[a_id], old_ratings[b_id])
        exp_b = 1.0 - exp_a
        if a_id == full_winner_id:
            actual_a, actual_b = 1.0, 0.0
        elif b_id == full_winner_id:
            actual_a, actual_b = 0.0, 1.0
        else:
            actual_a, actual_b = 0.5, 0.5
        new_ratings[a_id] = tournament.update_elo(new_ratings[a_id], exp_a, actual_a)
        new_ratings[b_id] = tournament.update_elo(new_ratings[b_id], exp_b, actual_b)

    for cid, new_rating in new_ratings.items():
        registry.update_agent(cid, elo_rating=round(new_rating, 2))
        registry.update_stats(cid, won=(cid == full_winner_id))

    conn.commit()

    # Print results
    winner_agent = registry.get_agent(full_winner_id)
    print(f"Verdict recorded for match {mid[:8]}")
    print(f"Winner: {winner_agent.name if winner_agent else full_winner_id[:8]}")
    print()
    print("Elo updates:")
    for cid in updated_match.competitor_ids:
        agent = registry.get_agent(cid)
        name = agent.name if agent else cid[:8]
        old = old_ratings.get(cid, 1500)
        new = new_ratings.get(cid, 1500)
        delta = new - old
        sign = "+" if delta >= 0 else ""
        print(f"  {name}: {old:.0f} → {new:.0f} ({sign}{delta:.0f})")

    conn.close()


if __name__ == "__main__":
    main()
