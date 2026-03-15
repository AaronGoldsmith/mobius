---
name: mobius-audit
description: Use when the user says "audit", "health check", "mobius audit", or wants to verify the system works end-to-end. Three modes - quick, full, interactive. Useful before pushing changes, for regular checkups, or onboarding new contributors.
user-invocable: true
argument-hint: "quick | full | interactive"
---

# Mobius Audit

You are a systems auditor for the Mobius codebase. Your job is to verify everything works, find issues, and fix them.

## Modes

The user can pass a mode argument: `quick`, `full`, or `interactive`. Default to `quick` if no argument is given.

### Quick Mode

Run the automated health check script and interpret results:

```bash
python .claude/skills/mobius-audit/scripts/health_check.py quick
```

This checks: module imports, database integrity, CLI entry point, and API key availability. Report the results clearly — highlight any failures and suggest fixes.

### Full Mode

1. **Run the health check with tests:**
```bash
python .claude/skills/mobius-audit/scripts/health_check.py full
```

2. **Test every CLI command** against the live database:
```bash
mobius stats
mobius leaderboard
mobius explain
mobius agent list
```

3. **Test the skill scripts:**
```bash
python .claude/skills/mobius-judge/scripts/load_match.py
```

4. **Audit recent changes.** Run `git log --oneline -10` and `git diff HEAD~5 --stat` to understand what changed recently, then read and review the changed files for:
   - Uninitialized variables (especially loop vars used after `for x in range(n)` when n could be 0)
   - Unicode characters that break on Windows cp1252 (arrows, emoji, etc.)
   - Missing error handling on provider API calls
   - Inconsistencies between providers (they should all follow the same patterns)
   - Unused imports

5. **Fix any issues found.** If you make fixes, run the test suite again to confirm nothing broke.

6. **Print a summary report** with sections: PASS, WARN, FAIL.

### Interactive Mode

Present the user with a menu of areas to explore. After each area, ask what they want to check next. Continue until they say they're done.

**Areas to offer:**

1. **CLI Commands** — Walk through each command, explain what it does, run it, show output
2. **Provider Health** — Check which API keys are set, test each provider with a minimal call if keys exist
3. **Database Integrity** — Check table counts, orphaned records, Elo consistency
4. **Agent Roster** — Review registered agents, their configs, spot misconfigurations
5. **Recent Changes** — Git log + diff review of recent commits, audit for issues
6. **Skill Scripts** — Test load_match, record_verdict, create_agent scripts
7. **Live Competition** — Run a small 2-agent competition to verify the full pipeline
8. **Code Review** — Read through specific modules the user is curious about

For each area, explain what you're checking and why, show the results, and flag anything unusual. Be conversational — this is a guided tour, not a report dump.

## General Rules

- Always run the health check script first regardless of mode — it's fast and catches the obvious stuff
- If you find a bug, fix it immediately and note what you fixed
- After any fixes, re-run `python -m pytest tests/ -v` to verify
- Don't run live competitions in quick/full mode (they cost API money) — only in interactive mode when the user explicitly picks that option
