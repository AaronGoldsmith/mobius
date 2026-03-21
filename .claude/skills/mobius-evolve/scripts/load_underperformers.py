commit fe66e75cc7f79b4ed77b2c8490f4e19862924bad
Author: Aaron Goldsmith <aargoldsmith@gmail.com>
Date:   Sat Mar 21 09:13:05 2026 -0700

    Add agentic competition tasks, agent definitions, and skills
    
    - Agent definitions: competition-tasks, depth-test, tree-solver
    - Skills: mobius-evolve (free Opus evolution), tree-solve (recursive decomposition)
    - Competition tasks: standard + agentic (tool-heavy, multi-tier)
    - Cleanup script for dead-weight agents
    - Fix hardcoded paths in agentic tasks to use relative paths
    - Make system monitoring task cross-platform (Unix tools)
    - Remove unused import in cleanup_agents.py
    - Add .tree-workspace/ to .gitignore
    
    Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

diff --git a/.claude/skills/mobius-evolve/scripts/load_underperformers.py b/.claude/skills/mobius-evolve/scripts/load_underperformers.py
new file mode 100644
index 0000000..797ee6d
--- /dev/null
+++ b/.claude/skills/mobius-evolve/scripts/load_underperformers.py
@@ -0,0 +1,108 @@
+"""Load underperforming agents with their loss feedback for evolution.
+
+Usage:
+    python load_underperformers.py [specialization] [--threshold 0.4] [--min-matches 3]
+
+Outputs agent details, win rates, and judge feedback from their losses
+so that Opus can craft improved system prompts.
+"""
+
+import json
+import sys
+
+sys.path.insert(0, "src")
+
+from mobius.config import get_config
+from mobius.db import init_db, row_to_dict
+from mobius.registry import Registry
+from mobius.tournament import Tournament
+
+
+def main():
+    args = sys.argv[1:]
+
+    # Parse flags
+    specialization = None
+    threshold = 0.4
+    min_matches = 3
+
+    i = 0
+    while i < len(args):
+        if args[i] == "--threshold" and i + 1 < len(args):
+            threshold = float(args[i + 1])
+            i += 2
+        elif args[i] == "--min-matches" and i + 1 < len(args):
+            min_matches = int(args[i + 1])
+            i += 2
+        elif not args[i].startswith("--"):
+            specialization = args[i]
+            i += 1
+        else:
+            i += 1
+
+    config = get_config()
+    conn, _ = init_db(config)
+    registry = Registry(conn, config)
+    tournament = Tournament(conn, config, registry)
+
+    agents = registry.list_agents(specialization=specialization)
+    if not agents:
+        print(f"No agents found{' for ' + specialization if specialization else ''}.")
+        sys.exit(1)
+
+    underperformers = []
+    for agent in agents:
+        if agent.total_matches < min_matches:
+            continue
+        win_rate = tournament.get_agent_recent_win_rate(
+            agent.id, window=config.underperformer_window
+        )
+        if win_rate < threshold:
+            underperformers.append((agent, win_rate))
+
+    if not underperformers:
+        print(f"No underperformers below {threshold:.0%} win rate (min {min_matches} matches).")
+        print("\nAll agents:")
+        for agent in agents:
+            wr = tournament.get_agent_recent_win_rate(agent.id, window=config.underperformer_window)
+            print(f"  {agent.name} ({agent.slug}) — {wr:.0%} win rate, {agent.total_matches} matches")
+        sys.exit(0)
+
+    print(f"UNDERPERFORMERS (below {threshold:.0%} win rate, min {min_matches} matches)")
+    print(f"Found: {len(underperformers)}")
+    print()
+
+    for agent, win_rate in underperformers:
+        matches = tournament.get_agent_matches(agent.id, limit=10)
+        losses = [m for m in matches if m.winner_id != agent.id and not m.voided]
+
+        print(f"{'='*70}")
+        print(f"AGENT: {agent.name}")
+        print(f"  Slug: {agent.slug}")
+        print(f"  ID: {agent.id}")
+        print(f"  Provider: {agent.provider}/{agent.model}")
+        print(f"  Win Rate: {win_rate:.0%} (Elo: {agent.elo_rating:.0f})")
+        print(f"  Generation: {agent.generation}")
+        print(f"  Specializations: {', '.join(agent.specializations)}")
+        print(f"  Losses: {len(losses)}")
+        print()
+        print("  CURRENT SYSTEM PROMPT:")
+        print(f"  {agent.system_prompt}")
+        print()
+
+        if losses:
+            print("  JUDGE FEEDBACK FROM LOSSES:")
+            for j, m in enumerate(losses[:5], 1):
+                print(f"  --- Loss {j} ---")
+                print(f"  Task: {m.task_description[:150]}")
+                if m.judge_reasoning:
+                    print(f"  Judge: {m.judge_reasoning[:300]}")
+                print()
+
+        print()
+
+    conn.close()
+
+
+if __name__ == "__main__":
+    main()
