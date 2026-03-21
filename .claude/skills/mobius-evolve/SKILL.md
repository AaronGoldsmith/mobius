---
name: mobius-evolve
description: Use when the user says "evolve", "mobius evolve", "improve agents", or wants to refine underperforming agents without API costs.
user-invocable: true
argument-hint: "[specialization] [--threshold 0.4]"
---

# Mobius Evolve (Local Opus — Evaluator-Optimizer Loop)

**You ARE the evaluator-optimizer.** You are Claude Opus running locally — this costs $0 in API calls. Instead of calling the API to refine agents, YOU analyze the judge feedback, critique the current system prompt, and craft an improved version using the agentic-eval reflection pattern.

## Why this matters

The `mobius evolve` CLI command calls the Opus API to refine agents ($$$). But you (Claude Code Opus) are already running and are the same model. So:
- **This skill** = Opus refining agents for FREE (Pro subscription) with multi-pass self-critique
- **mobius evolve** = Opus refining agents for $$$ (API calls), single or multi-pass
- Same quality, zero cost, and you have full conversation context.

## What to do

### Step 1: Load underperformers

```bash
python .claude/skills/mobius-evolve/scripts/load_underperformers.py [specialization] [--threshold 0.4]
```

This shows agents with low win rates, their current system prompts, and judge feedback from their losses.

### Step 2: Analyze and refine (YOU are the evaluator-optimizer loop)

For each underperformer, apply the **reflection pattern**:

**Evaluate:** Read the agent's current system prompt and the judge feedback. Identify the specific weaknesses the judges called out.

**Critique:** Ask yourself:
- What specific failure patterns does the feedback reveal?
- Is the system prompt too generic? Too narrow? Missing edge cases?
- Does it lack clear quality criteria or output format expectations?
- Would a different problem-solving approach help?

**Refine:** Write an improved system prompt that directly addresses each criticism. Be substantive — cosmetic rewording doesn't help.

**Self-check:** Before registering, verify your refinement:
- Does it address EVERY piece of judge feedback?
- Is it specific and opinionated (not generic)?
- Does it include quality criteria, methodology, and output format?
- Is it meaningfully different from the original, not just reworded?

If your self-check fails, iterate — refine again before registering.

### Step 3: Register the improved agent

Use the create_agent script to register the evolved version:

```bash
python .claude/skills/mobius-seed/scripts/create_agent.py '{
  "name": "Agent Name v2",
  "slug": "original-slug-v2",
  "description": "Updated description",
  "system_prompt": "Your improved system prompt here...",
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "tools": ["Read", "Grep", "Glob", "Bash", "Write", "Edit"],
  "specializations": ["coding", "refactoring"],
  "is_champion": false
}'
```

Important:
- Set `is_champion` to `false` — the evolved agent must earn its rank through competition
- Keep the same provider/model unless there's a strong reason to change
- Use a slug like `original-slug-v2` or `original-slug-gen2` to show lineage
- Keep the same specializations

### Step 4: Show results

```bash
python -m mobius.cli agent list
```

## The Agentic-Eval Pattern You're Running

```
Load underperformers → Read judge feedback → Critique prompt
    ↑                                            ↓
    └──── Self-check fails? ← Refine prompt ←───┘
                                    ↓
                            Self-check passes
                                    ↓
                            Register agent
```

This is the Evaluator-Optimizer pattern from agentic-eval, with YOU as both evaluator and optimizer. The key advantage over the CLI version: you can reason about the feedback in full context, consider the agent's match history, and make nuanced improvements that a single API call might miss.

## Pro Tips

- **Don't just reword** — change the agent's methodology, add specific techniques, restructure the approach
- **Study the winners** — if the judge praised a winning agent's approach, consider incorporating similar strategies
- **Vary approaches** — if an agent keeps losing with approach X, try a fundamentally different approach Y
- **Keep prompts focused** — under 2000 tokens but dense with specific guidance
- **Consider the model** — Haiku benefits from very explicit instructions; Gemini Flash may need different prompt styles
