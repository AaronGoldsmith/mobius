"""Create an agent from JSON input and register it in the Mobius database.

Usage:
    python create_agent.py '<json>'

The JSON should have these fields:
    name          - Display name (e.g. "Python Optimizer")
    slug          - Kebab-case identifier (e.g. "python-optimizer")
    description   - One-line description of when to use this agent
    system_prompt - The full system prompt
    provider      - "anthropic", "google", "openai", or "openrouter"
    model         - Model ID (e.g. "claude-haiku-4-5-20251001", "gemini-2.5-flash")
    tools         - List of tool names (default: ["Read", "Grep", "Glob", "Bash"])
    specializations - List of specialization tags (e.g. ["coding", "python"])
    is_champion   - Whether to mark as champion (default: true)
"""

import json
import sys

sys.path.insert(0, "src")

from mobius.config import get_config
from mobius.db import init_db
from mobius.models import AgentRecord
from mobius.registry import Registry


def main():
    if len(sys.argv) < 2:
        print("Usage: python create_agent.py '<json>'")
        print("Pass agent definition as a JSON string.")
        sys.exit(1)

    data = json.loads(sys.argv[1])

    # Validate required fields
    required = ["name", "slug", "description", "system_prompt"]
    missing = [f for f in required if f not in data]
    if missing:
        print(f"Missing required fields: {', '.join(missing)}")
        sys.exit(1)

    config = get_config()
    conn, vec_available = init_db(config)
    registry = Registry(conn, config, vec_available)

    # Check for duplicates
    existing = registry.get_agent_by_slug(data["slug"])
    if existing:
        print(f"Agent '{data['slug']}' already exists (id={existing.id[:8]}). Skipping.")
        conn.close()
        return

    agent = AgentRecord(
        name=data["name"],
        slug=data["slug"],
        description=data["description"],
        system_prompt=data["system_prompt"],
        provider=data.get("provider", "anthropic"),
        model=data.get("model", "claude-haiku-4-5-20251001"),
        tools=data.get("tools", ["Read", "Grep", "Glob", "Bash"]),
        specializations=data.get("specializations", []),
        is_champion=data.get("is_champion", True),
    )

    registry.create_agent(agent)
    print(f"Created: {agent.name}")
    print(f"  Slug: {agent.slug}")
    print(f"  Provider: {agent.provider}/{agent.model}")
    print(f"  Specializations: {', '.join(agent.specializations)}")
    print(f"  ID: {agent.id}")

    conn.close()


if __name__ == "__main__":
    main()
