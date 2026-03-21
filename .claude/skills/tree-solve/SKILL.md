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

diff --git a/.claude/skills/tree-solve/SKILL.md b/.claude/skills/tree-solve/SKILL.md
new file mode 100644
index 0000000..1082d58
--- /dev/null
+++ b/.claude/skills/tree-solve/SKILL.md
@@ -0,0 +1,135 @@
+---
+name: tree-solve
+description: Recursive task decomposition using a tree of agents. Use when the user says "tree solve", "decompose this", "break this down", or has a complex multi-part task that benefits from hierarchical delegation.
+user-invocable: true
+argument-hint: <complex task description> [--depth N] [--model MODEL]
+---
+
+# Tree Solver — Recursive Task Decomposition
+
+You are launching a **tree-solver** session: a recursive agent system that decomposes complex tasks into subtasks, delegates each to child agents, and aggregates results back up the tree.
+
+## How it works
+
+```
+You (main thread, orchestrator)
+  ├── spawns Agent A (subtask 1) ──→ may spawn its own child processes
+  ├── spawns Agent B (subtask 2) ──→ may spawn its own child processes
+  └── aggregates all results into final output
+```
+
+Each level can either **execute directly** (leaf node) or **decompose further** by launching `claude --agent tree-solver` as a background process, creating true recursion.
+
+## Parse arguments
+
+- **Task**: The main argument (required)
+- **--depth N**: Max recursion depth (default: 2). Higher = more decomposition. Recommend 2-3.
+- **--model MODEL**: Model for child solvers (default: sonnet). Use `haiku` for cheaper runs.
+
+## Step 1: Set up workspace
+
+```bash
+SESSION_ID="tree-$(date +%Y%m%d-%H%M%S)"
+WORKSPACE="$(pwd)/.tree/${SESSION_ID}"
+mkdir -p "${WORKSPACE}/root"
+```
+
+Tell the user the session ID and workspace path.
+
+## Step 2: Analyze the task
+
+Before decomposing, think about the task:
+- What are the **natural seams** where this splits into independent work?
+- Is decomposition actually valuable here, or should you just do it directly?
+- What's the right granularity? (2-4 subtasks per level is ideal)
+
+If the task is simple enough to do directly, skip decomposition — just do it and write the result.
+
+## Step 3: Decompose (if warranted)
+
+Write a decomposition plan to `{WORKSPACE}/root/plan.md`:
+- List each subtask with a clear, self-contained description
+- Note dependencies between subtasks (if any)
+- Describe how results will be aggregated
+
+## Step 4: Spawn child solvers
+
+For each subtask, create the child's task file and launch it.
+
+**For independent subtasks — launch in parallel:**
+
+```bash
+mkdir -p "{WORKSPACE}/root-1"
+# Write the task file
+cat > "{WORKSPACE}/root-1/task.md" << 'EOF'
+TREE_TASK: {detailed subtask description with full context}
+TREE_NODE: root-1
+TREE_DEPTH: 1
+TREE_MAX_DEPTH: {max_depth}
+TREE_WORKSPACE: {WORKSPACE}
+TREE_CONTEXT: {what the parent task is, how this subtask fits in}
+EOF
+```
+
+Then spawn the child solver process:
+
+```bash
+claude -p "$(cat {WORKSPACE}/root-1/task.md)" --agent tree-solver --model {MODEL} --max-turns 30 > "{WORKSPACE}/root-1/output.log" 2>&1 &
+```
+
+**IMPORTANT**: Launch independent children in the background with `&` and use `wait` to collect them all.
+
+For subtasks with dependencies, launch sequentially.
+
+## Step 5: Monitor and collect
+
+```bash
+wait  # Wait for all background children to complete
+```
+
+Then check each child's results:
+```bash
+for child_dir in {WORKSPACE}/root-*/; do
+  echo "=== $(basename $child_dir) ==="
+  if [ -f "$child_dir/result.md" ]; then
+    cat "$child_dir/result.md"
+  else
+    echo "NO RESULT — check $child_dir/output.log"
+  fi
+done
+```
+
+## Step 6: Aggregate
+
+Read all child results and synthesize them into a coherent final output. Write to `{WORKSPACE}/root/result.md`.
+
+Consider:
+- Did all children succeed? Handle partial failures gracefully.
+- Do the pieces fit together? Resolve any conflicts or gaps.
+- Is the combined result better than what a single agent would have produced?
+
+## Step 7: Present to user
+
+Show:
+1. **The tree structure** — which nodes decomposed, which executed
+2. **The final result** — the aggregated output
+3. **Stats** — how many agents were involved, depth reached, any failures
+
+```bash
+echo "=== Tree Structure ==="
+find {WORKSPACE} -name "*.md" | sort
+echo ""
+echo "=== Final Result ==="
+cat {WORKSPACE}/root/result.md
+```
+
+## Guidelines
+
+- **Depth 1** is great for most tasks (split into 2-4 pieces, execute each)
+- **Depth 2** for genuinely complex tasks (architecture + implementation + testing)
+- **Depth 3** rarely needed — only for massive scope
+- **Context is everything**: Each child must have enough context to work independently. Over-communicate in task descriptions.
+- **Don't decompose for the sake of it**: If a subtask at any level is atomic, just execute it.
+- **Workspace discipline**: All files go in the workspace. This makes it easy to inspect, debug, and clean up.
+- **Never delete `.tree/` wholesale** — other sessions may be active. Only clean up your own session: `rm -rf .tree/{SESSION_ID}/`. Always confirm the session ID before deleting.
+- Before cleanup, check if other sessions exist: `ls .tree/` — if there are directories besides yours, leave them alone.
