"""Record agent outputs for a free competition match.

Usage:
    python record_outputs.py <match_id> <outputs_json>

The outputs_json maps agent IDs to their output text:
    '{"agent_id_1": "output text...", "agent_id_2": "output text..."}'
"""

import json
import sys

sys.path.insert(0, "src")

from mobius.config import get_config
from mobius.db import init_db


def main():
    if len(sys.argv) < 3:
        print("Usage: python record_outputs.py <match_id> '<outputs_json>'")
        sys.exit(1)

    match_id = sys.argv[1]
    outputs = json.loads(sys.argv[2])

    config = get_config()
    conn, _ = init_db(config)

    row = conn.execute("SELECT id FROM matches WHERE id LIKE ?", (f"{match_id}%",)).fetchone()
    if not row:
        print(f"Match '{match_id}' not found.")
        sys.exit(1)

    full_id = row[0]
    conn.execute(
        "UPDATE matches SET outputs = ? WHERE id = ?",
        (json.dumps(outputs), full_id),
    )
    conn.commit()
    print(f"Recorded {len(outputs)} outputs for match {full_id[:8]}")
    conn.close()


if __name__ == "__main__":
    main()
