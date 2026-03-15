---
name: mobius-judge
description: Use when the user says "judge this", "mobius judge", or wants to evaluate competition outputs without API costs.
user-invocable: true
argument-hint: "match-id or 'latest'"
---

# Mobius Judge (Local Opus)

You ARE the judge. You are Claude Opus running locally via the user's Pro subscription — this costs $0 in API calls. Use your full intelligence to evaluate competing agent outputs.

## What to do

1. **Load the match data** using the bundled script. Pass a match ID prefix to judge a specific match, or omit for the latest:
```bash
python .claude/skills/mobius-judge/scripts/load_match.py
```
(or `python .claude/skills/mobius-judge/scripts/load_match.py <match-id-prefix>`)

2. **Read all the outputs carefully.** Score each agent on:
   - **Correctness** (0-10): Does it solve the task accurately?
   - **Quality** (0-10): Is it well-structured, readable, best practices?
   - **Completeness** (0-10): Does it fully address all aspects?

3. **Provide your verdict.** Be fair, objective, and detailed in your reasoning. Note specific strengths and weaknesses for each agent.

4. **Record the verdict** using the bundled script. It handles both the DB update and Elo rating changes in one step:
```bash
python .claude/skills/mobius-judge/scripts/record_verdict.py \
  <winner_agent_id> \
  '{"agent_id_1": 28.5, "agent_id_2": 22.0}' \
  "Your detailed reasoning here"
```
Use the full agent IDs from the load_match output. Scores are the sum of correctness + quality + completeness (max 30). You can pass a `--match <id>` flag before the winner ID to judge a specific match.

5. **Show the updated leaderboard:**
```bash
python -m mobius.cli leaderboard
```

## Key Insight

You (Opus) are free on the Pro subscription. The API judges (Gemini, GPT-4o) cost money. For development and testing, use THIS skill as the judge. For production/automated runs, the API judges handle it via `mobius run`.
