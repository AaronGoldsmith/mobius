# Ideas

Concepts worth revisiting. Emerged from competitions, brainstorming, or usage patterns.

## Skills to Build

### `/mobius-forge` — Two-Phase Generate→Test Competition
Run a competition where agents produce artifacts (code, skills, configs), then a second wave of agents functionally tests those artifacts. Scores combine design quality and working reality. This was the most valuable pattern from the 2026-03-14 skill forge lab.

### Match Replay / Post-Mortem
After a competition, automatically analyze: why did the winner win? What specific weaknesses caused losses? Extract judge feedback into actionable evolution targets. Closes the run→evolve feedback loop. (Attempted in skill forge — concept was strong, execution had bugs.)

## System Improvements

### Agent Factory Agent
An agent whose specialization is creating other agents. It identifies capability gaps, designs the agent (system prompt, tools, specializations), and registers it directly. Different from `/mobius-seed` because it's autonomous — it decides what's needed.

### Self-Audit Competition
A competition where agents identify Mobius's own limitations and propose fixes. Winning proposals get implemented. Like `/mobius-audit` but adversarial and focused on improvement proposals rather than health checks.

### `mobius improve` Command
Takes the winning output from a "system improvement" competition and applies it. Closes the loop: compete → judge → implement → re-audit → repeat.

## Observations

- Smiths (codebase analysis) consistently outperform scouts (web research) on tasks about THIS project
- Minimalist agents produce more reliable code than ambitious ones
- Haiku agents over-promise in documentation vs. what their code actually does
- The `tools` field in agent DB is metadata only — subagents get all tools regardless
- Web research agents (WebSearch/WebFetch) DO work in subagents but scouts didn't leverage them effectively
