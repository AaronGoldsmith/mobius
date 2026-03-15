"""Load the latest match data for judging. Outputs task, agent names, and their outputs."""

import json
import sys

sys.path.insert(0, "src")

from mobius.config import get_config
from mobius.db import init_db, row_to_dict
from mobius.registry import Registry


def main(match_id: str | None = None):
    config = get_config()
    conn, _ = init_db(config)
    registry = Registry(conn, config)

    if match_id:
        row = conn.execute("SELECT * FROM matches WHERE id LIKE ?", (f"{match_id}%",)).fetchone()
    else:
        row = conn.execute("SELECT * FROM matches ORDER BY created_at DESC LIMIT 1").fetchone()

    if not row:
        print("No matches found. Run a competition first: mobius run <task>")
        sys.exit(1)

    match = row_to_dict(row)
    outputs = match.get("outputs", {})
    if isinstance(outputs, str):
        outputs = json.loads(outputs)

    print(f"MATCH: {match['id']}")
    print(f"TASK: {match['task_description']}")
    print(f"COMPETITORS: {len(outputs)}")
    print()

    for agent_id, output in outputs.items():
        agent = registry.get_agent(agent_id)
        name = agent.name if agent else agent_id[:8]
        slug = agent.slug if agent else "unknown"
        print(f"--- AGENT: {name} (slug={slug}, id={agent_id}) ---")
        print(output)
        print()

    conn.close()


if __name__ == "__main__":
    mid = sys.argv[1] if len(sys.argv) > 1 else None
    main(mid)
