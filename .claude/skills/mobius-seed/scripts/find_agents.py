"""Find agents semantically similar to a query.

Usage:
    python find_agents.py "build a REST API with authentication"
    python find_agents.py "debug memory leaks" --top 5

Returns JSON array of matching agents ranked by relevance.
"""

import json
import sys

sys.path.insert(0, "src")

from mobius.config import get_config
from mobius.db import init_db, vec_to_blob
from mobius.embedder import embed
from mobius.registry import Registry


def main():
    if len(sys.argv) < 2:
        print("Usage: python find_agents.py '<query>' [--top N]")
        sys.exit(1)

    query = sys.argv[1]
    top_k = 10
    if "--top" in sys.argv:
        idx = sys.argv.index("--top")
        if idx + 1 < len(sys.argv):
            top_k = int(sys.argv[idx + 1])

    config = get_config()
    conn, vec_available = init_db(config)

    if not vec_available:
        print(json.dumps({"error": "sqlite-vec not available"}))
        sys.exit(1)

    # Check if agent_vec has any rows
    count = conn.execute("SELECT COUNT(*) as cnt FROM agent_vec").fetchone()["cnt"]
    if count == 0:
        print(json.dumps({"error": "No agent embeddings found. Run backfill first."}))
        sys.exit(1)

    # Embed query and search
    query_vec = embed(query, config)
    query_blob = vec_to_blob(query_vec)

    rows = conn.execute(
        """
        SELECT av.id, av.distance
        FROM agent_vec av
        WHERE av.description_embedding MATCH ?
            AND k = ?
        ORDER BY av.distance
        """,
        (query_blob, top_k),
    ).fetchall()

    if not rows:
        print(json.dumps([]))
        conn.close()
        return

    # Fetch full agent details for matches
    registry = Registry(conn, config, vec_available)
    results = []
    for row in rows:
        agent = registry.get_agent(row["id"])
        if agent is None:
            continue
        distance = row["distance"]
        similarity = 1.0 - (distance**2 / 2.0)
        results.append({
            "slug": agent.slug,
            "name": agent.name,
            "description": agent.description,
            "provider": agent.provider,
            "model": agent.model,
            "specializations": agent.specializations,
            "elo": round(agent.elo_rating),
            "win_rate": round(agent.win_rate, 3),
            "matches": agent.total_matches,
            "champion": agent.is_champion,
            "similarity": round(similarity, 4),
        })

    print(json.dumps(results, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
