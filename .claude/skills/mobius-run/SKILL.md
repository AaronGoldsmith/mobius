---
name: mobius-run
description: Use when the user says "compete", "mobius run", or wants to pit agents against each other on a task.
user-invocable: true
argument-hint: <task description>
---

# Mobius Competition Runner

You are the orchestrator for Mobius, an adversarial agent swarm system. The user wants to run a competition.

## What to do

1. Check that Mobius is initialized:
```bash
python -m mobius.cli stats
```

2. If not initialized, run:
```bash
python -m mobius.cli init
```

3. If no agents exist, suggest running `/mobius-seed` first.

4. Run the competition with the user's task:
```bash
python -m mobius.cli run "<TASK>"
```

5. After the competition, show the explain output:
```bash
python -m mobius.cli explain
```

6. Present the winning output to the user along with the judge reasoning.

If the user didn't provide a task argument, ask them what they want the agents to compete on.
