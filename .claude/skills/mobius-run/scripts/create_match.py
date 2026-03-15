"""Create a match record for a free (subagent-based) competition.

Usage:
    python create_match.py "<task>" [--agents <slug1,slug2,...>] [--count N]

Modes:
    --agents slug1,slug2   Use specific agents from registry by slug
    --count N              Pick top N agents by Elo (default: 5)

Outputs JSON with match_id and agent details for the skill to orchestrate.
"""

import json
import sys

sys.path.insert(0, "src")

from mobius.config import get_config
from mobius.db import init_db
from mobius.models import MatchRecord
from mobius.registry import Registry


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python create_match.py '<task>' [--agents s1,s2] [--count N]")
        sys.exit(1)

    task = args[0]
    slugs = None
    count = 5

    i = 1
    while i < len(args):
        if args[i] == "--agents" and i + 1 < len(args):
            slugs = [s.strip() for s in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--count" and i + 1 < len(args):
            count = int(args[i + 1])
            i += 2
        else:
            i += 1

    config = get_config()
    conn, _ = init_db(config)
    registry = Registry(conn, config)

    # Select agents
    agents = []
    if slugs:
        for slug in slugs:
            agent = registry.get_agent_by_slug(slug)
            if agent:
                agents.append(agent)
            else:
                print(f"Warning: agent '{slug}' not found, skipping")
    else:
        all_agents = registry.list_agents()
        all_agents.sort(key=lambda a: a.elo_rating, reverse=True)
        agents = all_agents[:count]

    if len(agents) < 2:
        print(json.dumps({"error": "Need at least 2 agents", "agent_count": len(agents)}))
        sys.exit(1)

    # Create match record (outputs empty — skill will fill them)
    match = MatchRecord(
        task_description=task,
        competitor_ids=[a.id for a in agents],
    )

    conn.execute(
        """INSERT INTO matches (id, task_description, competitor_ids, outputs, judge_models,
            judge_reasoning, winner_id, scores, voided, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            match.id,
            match.task_description,
            json.dumps(match.competitor_ids),
            json.dumps({}),
            json.dumps([]),
            "",
            None,
            json.dumps({}),
            0,
            match.created_at.isoformat(),
        ),
    )
    conn.commit()

    # Output agent details for the skill
    result = {
        "match_id": match.id,
        "task": task,
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "slug": a.slug,
                "system_prompt": a.system_prompt,
                "specializations": a.specializations,
                "elo_rating": a.elo_rating,
            }
            for a in agents
        ],
    }

    print(json.dumps(result, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
