"""Clean dead weight agents and fix champion flags in the Mobius registry."""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/mobius.db")


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def list_zero_match_agents(conn: sqlite3.Connection) -> list[dict]:
    """Find agents with 0 total matches."""
    rows = conn.execute(
        "SELECT id, name, slug, elo_rating, is_champion, created_at "
        "FROM agents WHERE total_matches = 0 ORDER BY created_at"
    ).fetchall()
    return [dict(r) for r in rows]


def list_champions(conn: sqlite3.Connection) -> list[dict]:
    """Find agents marked as champions with their stats."""
    rows = conn.execute(
        "SELECT id, name, slug, is_champion, elo_rating, win_rate, total_matches "
        "FROM agents WHERE is_champion = 1 ORDER BY elo_rating DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def list_all_agents_summary(conn: sqlite3.Connection) -> list[dict]:
    """Quick summary of all agents."""
    rows = conn.execute(
        "SELECT id, name, slug, elo_rating, win_rate, total_matches, is_champion "
        "FROM agents ORDER BY elo_rating DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def retire_zero_match_agents(conn: sqlite3.Connection) -> int:
    """Set elo_rating=0 and is_champion=0 for agents with 0 matches."""
    cursor = conn.execute(
        "UPDATE agents SET elo_rating = 0.0, is_champion = 0 "
        "WHERE total_matches = 0"
    )
    conn.commit()
    return cursor.rowcount


def clear_all_champion_flags(conn: sqlite3.Connection) -> int:
    """Clear is_champion on all agents."""
    cursor = conn.execute("UPDATE agents SET is_champion = 0 WHERE is_champion = 1")
    conn.commit()
    return cursor.rowcount



def elect_champions(conn: sqlite3.Connection) -> int:
    """Re-elect the highest-Elo agent per specialization as champion."""
    import json as _json
    rows = conn.execute(
        "SELECT id, specializations, elo_rating FROM agents "
        "WHERE total_matches > 0 AND elo_rating > 0 ORDER BY elo_rating DESC"
    ).fetchall()
    best_per_spec: dict[str, tuple[str, float]] = {}
    for r in rows:
        agent_id = r["id"]
        elo = r["elo_rating"]
        specs = _json.loads(r["specializations"]) if r["specializations"] else []
        for spec in specs:
            if spec not in best_per_spec or elo > best_per_spec[spec][1]:
                best_per_spec[spec] = (agent_id, elo)
    champion_ids = set(aid for aid, _ in best_per_spec.values())
    elected = 0
    for cid in champion_ids:
        conn.execute("UPDATE agents SET is_champion = 1 WHERE id = ?", (cid,))
        elected += 1
    conn.commit()
    return elected


def main():
    parser = argparse.ArgumentParser(description="Clean dead weight agents and fix champion flags")
    parser.add_argument("--execute", action="store_true", help="Actually apply changes (default is dry-run)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to mobius.db")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: Database not found at {args.db}")
        sys.exit(1)

    conn = get_connection(args.db)
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== Mobius Agent Cleanup [{mode}] ===\n")

    # Summary
    all_agents = list_all_agents_summary(conn)
    print(f"Total agents in registry: {len(all_agents)}\n")

    # Zero-match agents
    zero_match = list_zero_match_agents(conn)
    print(f"--- Agents with 0 matches ({len(zero_match)}) ---")
    if zero_match:
        for a in zero_match:
            champ_flag = " [CHAMPION]" if a["is_champion"] else ""
            print(f"  {a['slug']:30s}  elo={a['elo_rating']:7.1f}{champ_flag}  created={a['created_at']}")
    else:
        print("  (none)")
    print()

    # Champions
    champions = list_champions(conn)
    print(f"--- Current champions ({len(champions)}) ---")
    if champions:
        for a in champions:
            print(f"  {a['slug']:30s}  elo={a['elo_rating']:7.1f}  win_rate={a['win_rate']:.2%}  matches={a['total_matches']}")
    else:
        print("  (none)")
    print()

    if not args.execute:
        print("[DRY-RUN] No changes made. Re-run with --execute to apply.")
        print(f"  Would retire {len(zero_match)} zero-match agents (set elo=0, is_champion=0)")
        print(f"  Would clear is_champion flag on {len(champions)} agents")
    else:
        retired = retire_zero_match_agents(conn)
        cleared = clear_all_champion_flags(conn)
        print(f"[EXECUTE] Retired {retired} zero-match agents (elo set to 0)")
        print(f"[EXECUTE] Cleared champion flag on {cleared} agents")
        elected = elect_champions(conn)
        print(f"[EXECUTE] Re-elected {elected} champion(s) (highest Elo per specialization)")
        print("Done.")

    conn.close()


if __name__ == "__main__":
    main()
