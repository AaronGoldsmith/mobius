---
name: mobius-profile
description: Use when you want to analyze a specific agent's performance history, recent matches, win/loss record, or find challenging opponents for an agent.
user-invocable: true
argument-hint: <agent-slug>
---

# Mobius Agent Profile

Get a detailed performance breakdown for a single agent: their Elo rating, win rate, recent matches, key wins and losses, and recommended challengers.

## What to do

1. **Load the agent profile:**
```bash
python .claude/skills/mobius-profile/scripts/show_profile.py <agent-slug>
```

This outputs:
- Basic stats: Elo, win rate, total matches, generation, specializations
- Last 10 matches with opponents and outcomes
- Top 3 opponents they beat (by frequency)
- Top 3 opponents who beat them (by frequency)
- Recommended challengers: agents with opposite specializations or high win rates they haven't faced

2. **Interpret the profile:**
   - **Elo rating**: 1500 = average. Above 1700 = expert tier. Below 1300 = improving.
   - **Win rate**: How often they win. Track trends — improving vs. declining?
   - **Match history**: Are they losing to specific types of agents?
   - **Recommended challengers**: These agents exploit gaps in this agent's strength profile.

3. **Make decisions:**
   - If win rate is dropping, the agent may need evolution (`/mobius-judge` to judge their recent losses, then `mobius evolve <spec>`)
   - If they beat a specific opponent often, they may be over-specialized
   - If recommended challengers are all from one provider (e.g., "all Google"), they may struggle with that provider's style

## Pro Tips

- Run profiles for your **champions** before entering a long-running tournament to understand their strengths
- Compare two agents side-by-side by running profiles for both and looking at their match history overlap
- If an agent has only 1-2 total matches, they need more tournament exposure before drawing conclusions
- The "recommended challengers" list is smart: it prioritizes agents you haven't faced and agents with complementary specializations
