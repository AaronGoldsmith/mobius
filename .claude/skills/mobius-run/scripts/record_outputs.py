"""Record agent outputs for a free competition match.

Usage:
    echo "output text" | python record_outputs.py <match_id> <agent_id>
    echo '{"id1": "out1", "id2": "out2"}' | python record_outputs.py <match_id> --bulk

Reads output from stdin to avoid shell escaping issues.
"""

import json
import sys

sys.path.insert(0, "src")

from mobius.config import get_config
from mobius.db import init_db


def main():
    if len(sys.argv) < 3:
        print("Usage:", file=sys.stderr)
        print("  echo 'output' | python record_outputs.py <match_id> <agent_id>", file=sys.stderr)
        print("  echo '{...}' | python record_outputs.py <match_id> --bulk", file=sys.stderr)
        sys.exit(1)

    match_id = sys.argv[1]
    mode = sys.argv[2]
    stdin_data = sys.stdin.read()

    config = get_config()
    conn, _ = init_db(config)

    row = conn.execute(
        "SELECT id, outputs FROM matches WHERE id LIKE ?", (f"{match_id}%",)
    ).fetchone()
    if not row:
        print(f"Match '{match_id}' not found.", file=sys.stderr)
        sys.exit(1)

    full_id = row[0]
    existing = json.loads(row[1]) if row[1] else {}

    if mode == "--bulk":
        new_outputs = json.loads(stdin_data)
        existing.update(new_outputs)
    else:
        agent_id = mode
        existing[agent_id] = stdin_data.strip()

    conn.execute(
        "UPDATE matches SET outputs = ? WHERE id = ?",
        (json.dumps(existing), full_id),
    )
    conn.commit()
    print(f"Recorded {len(existing)} outputs for match {full_id[:8]}")
    conn.close()


if __name__ == "__main__":
    main()
