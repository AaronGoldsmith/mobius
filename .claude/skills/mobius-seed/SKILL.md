---
name: mobius-seed
description: Use when the user says "seed agents", "bootstrap mobius", "mobius seed", or wants to create initial agents without API costs.
user-invocable: true
argument-hint: "Specialization or codebase path"
allowed-tools: Bash, Read, Glob, Grep, Write, Edit
---

# Mobius Agent Seeder (Local Opus)

**You ARE the agent builder.** You are Claude Opus running on the user's Pro subscription — this costs $0 in API calls. Instead of calling the Opus API to generate agent definitions, YOU generate them directly with your full intelligence and context.

## Why this matters

The `agent_builder.py` module calls the Anthropic API (Opus) to generate agent prompts. That costs money. But you (Claude Code Opus) are already running and are the same model. So:
- **This skill** = Opus generating agents for FREE (Pro subscription)
- **agent_builder.py** = Opus generating agents for $$$ (API calls)
- Same quality, zero cost.

## What to do

1. **Initialize Mobius if needed:**
```bash
python -m mobius.cli init
```

2. **Check what already exists:**
```bash
python -m mobius.cli agent list
```

3. **Craft your agent definitions.** Think carefully about:
   - What makes a great system prompt for this specialization
   - Which provider/model is best suited (Haiku for speed, Gemini Flash for cost)
   - What tools the agent needs
   - Edge cases the agent should handle
   - Quality criteria the agent should self-check against

4. **Register each agent** using the bundled script:
```bash
python .claude/skills/mobius-seed/scripts/create_agent.py '{
  "name": "Python Optimizer",
  "slug": "python-optimizer",
  "description": "Specializes in Python performance optimization and profiling",
  "system_prompt": "You are a Python performance expert...",
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "tools": ["Read", "Grep", "Glob", "Bash", "Write", "Edit"],
  "specializations": ["coding", "python", "optimization"],
  "is_champion": true
}'
```

The script handles duplicate detection automatically — if a slug already exists, it skips.

5. **Repeat** for each agent. Create a diverse set across:
   - Different specializations (coding, review, testing, debugging, etc.)
   - Different providers (anthropic, google, openai) for tournament diversity
   - Different model tiers (haiku vs flash for cheap competitors)

6. **Show the final roster:**
```bash
python -m mobius.cli agent list
```

## Pro Tips

- **Mix providers**: Create some agents on Gemini Flash (very cheap) and some on Haiku. Let the tournament discover which is better.
- **Vary approaches**: Give agents different problem-solving styles (e.g., "think step by step" vs "output code immediately")
- **Be specific**: Generic prompts lose to specific ones in tournaments. "You are a Python expert who prioritizes readability" beats "You are a helpful coding assistant."
- If the user gives you a codebase path, READ the codebase first and create agents tailored to its tech stack, patterns, and common tasks.
