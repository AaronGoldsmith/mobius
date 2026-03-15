"""Show detailed performance profile for a single agent.

Usage:
    python show_profile.py <agent-slug>

Outputs: Basic stats, recent match history, win/loss analysis, and recommended challengers.
"""

import sys
from collections import Counter

sys.path.insert(0, "src")

from mobius.config import get_config
from mobius.db import init_db
from mobius.registry import Registry
from mobius.tournament import Tournament


def main():
    if len(sys.argv) < 2:
        print("Usage: python show_profile.py <agent-slug>")
        sys.exit(1)

    slug = sys.argv[1]
    config = get_config()
    conn, _ = init_db(config)
    registry = Registry(conn, config)
    tournament = Tournament(conn, config, registry)

    # Get agent
    agent = registry.get_agent_by_slug(slug)
    if not agent:
        print(f"Agent '{slug}' not found.")
        sys.exit(1)

    # ===== BASIC STATS =====
    print(f"\n{'='*60}")
    print(f"  AGENT PROFILE: {agent.name}")
    print(f"{'='*60}\n")

    print(f"Slug:              {agent.slug}")
    print(f"ID:                {agent.id[:8]}...")
    print(f"Provider:          {agent.provider}/{agent.model.split('/')[-1][:20]}")
    print(f"Specializations:   {', '.join(agent.specializations) if agent.specializations else '(none)'}")
    print(f"Generation:        {agent.generation}")
    if agent.parent_id:
        parent = registry.get_agent(agent.parent_id)
        parent_name = parent.name if parent else agent.parent_id[:8]
        print(f"Parent:            {parent_name}")
    print(f"Champion:          {'Yes' if agent.is_champion else 'No'}")
    print()

    # ===== PERFORMANCE STATS =====
    print(f"Elo Rating:        {agent.elo_rating:.0f}")
    print(f"Win Rate:          {agent.win_rate:.1%} ({int(agent.win_rate * agent.total_matches)}/{agent.total_matches} matches)")
    print(f"Total Matches:     {agent.total_matches}")
    print()

    # ===== RECENT MATCHES =====
    matches = tournament.get_agent_matches(agent.id, limit=10)
    if matches:
        print(f"{'='*60}")
        print(f"  RECENT MATCHES (last 10)")
        print(f"{'='*60}\n")

        opponent_wins = Counter()  # keyed by slug
        opponent_losses = Counter()  # keyed by slug
        slug_to_name = {}  # slug -> display name

        for i, match in enumerate(matches, 1):
            # Skip voided/undecided matches
            if match.winner_id is None:
                continue

            is_win = match.winner_id == agent.id
            outcome = "WIN " if is_win else "LOSS"

            # Find opponent(s)
            opponents = [cid for cid in match.competitor_ids if cid != agent.id]
            opponent_names = []
            for opp_id in opponents:
                opp = registry.get_agent(opp_id)
                opp_slug = opp.slug if opp else opp_id[:8]
                opp_name = opp.name if opp else opp_id[:8]
                slug_to_name[opp_slug] = opp_name
                opponent_names.append(opp_name)

                if is_win:
                    opponent_wins[opp_slug] += 1
                elif opp_id == match.winner_id:
                    # Only count loss against the actual winner
                    opponent_losses[opp_slug] += 1

            vs_text = " vs ".join(opponent_names)
            task_preview = match.task_description[:50].replace("\n", " ")
            print(f"{i:2}. [{outcome}] {vs_text}")
            print(f"    Task: {task_preview}{'...' if len(match.task_description) > 50 else ''}")
            print()

        # ===== WIN/LOSS ANALYSIS =====
        print(f"{'='*60}")
        print(f"  WIN/LOSS ANALYSIS")
        print(f"{'='*60}\n")

        if opponent_wins:
            print(f"Defeated most often:")
            for slug, count in opponent_wins.most_common(3):
                print(f"  • {slug_to_name.get(slug, slug)} ({count}x)")
            print()

        if opponent_losses:
            print(f"Lost to most often:")
            for slug, count in opponent_losses.most_common(3):
                print(f"  • {slug_to_name.get(slug, slug)} ({count}x)")
            print()

    else:
        print(f"No matches yet. Agent needs tournament exposure.")
        print()

    # ===== RECOMMENDED CHALLENGERS =====
    print(f"{'='*60}")
    print(f"  RECOMMENDED CHALLENGERS")
    print(f"{'='*60}\n")

    # Get all agents
    all_agents = registry.list_agents()

    # Filter: exclude self, exclude agents in recent matches
    recent_opponent_ids = set()
    if matches:
        for match in matches:
            recent_opponent_ids.update(match.competitor_ids)

    candidates = [
        a for a in all_agents
        if a.id != agent.id and a.id not in recent_opponent_ids
        and a.elo_rating > 0 and a.total_matches > 0
    ]

    if not candidates:
        print("No unused challengers available.")
        print()
    else:
        # Score candidates: prefer high win rate + different specializations
        scored = []
        agent_specs = set(agent.specializations)

        for cand in candidates:
            score = 0
            # High win rate (up to 50 points)
            score += int(cand.win_rate * 50)
            # Different specializations (up to 30 points)
            cand_specs = set(cand.specializations)
            if not (agent_specs & cand_specs):  # no overlap
                score += 30
            # High Elo (up to 20 points)
            score += int(min(cand.elo_rating / 2000 * 20, 20))

            scored.append((cand, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        for i, (cand, score) in enumerate(scored[:5], 1):
            specs = ", ".join(cand.specializations) if cand.specializations else "(none)"
            print(f"{i}. {cand.name}")
            print(f"   Elo: {cand.elo_rating:.0f} | Win Rate: {cand.win_rate:.1%}")
            print(f"   Specializations: {specs}")
            print()

    conn.close()


if __name__ == "__main__":
    main()
