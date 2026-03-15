---
name: mobius-run
description: Use when the user says "compete", "mobius run", or wants to pit agents against each other on a task.
user-invocable: true
argument-hint: <task description> [--free] [--api]
---

# Mobius Competition Runner

You are the orchestrator for Mobius, an adversarial agent swarm system. The user wants to run a competition.

## Determine mode

- **`--free`** (DEFAULT): Run the competition entirely within Claude Code using subagents. Zero API cost. You generate challenger personas on the fly, spawn them as haiku subagents, collect outputs, and judge them yourself.
- **`--api`**: Run via the CLI with real API calls (cross-family diversity, costs money).

If neither flag is given, default to `--free` mode.

---

## MODE: --free (Subagent Competition)

This is the exciting part. You ARE the competition engine — no API calls needed.

### Step 1: Initialize

```bash
python -m mobius.cli stats
```

If not initialized: `python -m mobius.cli init`

### Step 2: Choose agents

You have two options. Use whichever fits:

**Option A — Use existing agents from the registry:**
```bash
python .claude/skills/mobius-run/scripts/create_match.py "<TASK>" --count 6
```
This returns JSON with agent details including their system_prompts. Use these prompts for the subagents.

**Option B — Generate fresh challengers on the fly (PREFERRED for interesting results):**
Analyze the task and design 4-8 complementary approaches that attack it from deliberately different angles. Think about what dimensions of variation would produce genuinely diverse solutions — not just "creative vs analytical" but specific strategic differences relevant to THIS task.

For each challenger, create a short but specific system prompt (3-5 sentences) that defines their approach. Then register them:
```bash
python .claude/skills/mobius-seed/scripts/create_agent.py '{"name":"...", "slug":"...", "description":"...", "system_prompt":"...", "specializations":[...], "provider":"anthropic", "model":"claude-haiku-4-5-20251001"}'
```

Then create the match:
```bash
python .claude/skills/mobius-run/scripts/create_match.py "<TASK>" --agents slug1,slug2,slug3,...
```

**Option C — Mix both:** Pull veterans from the registry AND generate fresh challengers. Pit them against each other.

### Step 3: Spawn subagents

For each agent from the match JSON, spawn a haiku subagent using the Agent tool:
- Set `model: "haiku"` on each agent
- Pass the agent's system_prompt as context plus the competition task
- Use `subagent_type: "general-purpose"`
- **IMPORTANT: Launch ALL subagents in a SINGLE message** so they run in parallel
- Each subagent prompt should be structured as:

```
You are competing in a Mobius adversarial swarm competition.

YOUR IDENTITY AND APPROACH:
<the agent's system_prompt from the registry>

YOUR TASK:
<the competition task>

Produce your best solution. Be thorough but focused. Output ONLY your solution.
```

If you have more than 6 agents, batch them: spawn the first 6, wait for results, then spawn the next batch.

### Step 4: Record outputs

After each subagent returns, pipe its output to the match record:
```bash
echo "<agent_output>" | python .claude/skills/mobius-run/scripts/record_outputs.py <match_id> <agent_id>
```

You can record outputs incrementally as agents finish — each call merges into the existing record. Or record all at once with `--bulk`:
```bash
echo '<outputs_json>' | python .claude/skills/mobius-run/scripts/record_outputs.py <match_id> --bulk
```

### Step 5: Judge

You ARE the judge. Score each output on:
- **Correctness** (0-10): Does it solve the task accurately?
- **Quality** (0-10): Is it well-structured, readable, best practices?
- **Completeness** (0-10): Does it fully address all aspects?

Be ruthless and fair. Don't let positional bias affect you — judge purely on merit.

### Step 6: Record verdict

```bash
python .claude/skills/mobius-judge/scripts/record_verdict.py \
  --match <match_id> \
  <winner_agent_id> \
  '{"agent_id_1": 28.5, "agent_id_2": 22.0, ...}' \
  "Your detailed reasoning"
```

Use the match_id from Step 2 to ensure the verdict is recorded against the correct match.

### Step 7: Show results

```bash
python -m mobius.cli leaderboard
```

Present: the winner, your reasoning, Elo changes, and the winning solution.

---

## MODE: --api (CLI Competition)

Traditional mode using real API calls.

1. Check initialization:
```bash
python -m mobius.cli stats
```

2. If no agents exist, suggest `/mobius-seed` first.

3. Run the competition:
```bash
python -m mobius.cli run "<TASK>"
```

4. Show results:
```bash
python -m mobius.cli explain
```

5. Present the winning output and judge reasoning to the user.

---

## Tips

- For `--free` mode, you can scale to 12+ agents easily — haiku is fast and cheap (free on Pro)
- Generate challengers that are *orthogonal*, not just variations. Each should have a genuinely different strategy.
- If an existing champion agent loses to a fresh challenger, that's interesting — note it for the user
- The `--free` mode integrates with the same Elo system as `--api` — results are comparable
