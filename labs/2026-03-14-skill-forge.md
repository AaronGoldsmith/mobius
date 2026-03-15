# Lab: Skill Forge Competition

**Date:** 2026-03-14
**Match ID:** ed90f3e2f7c841d5b7538a17c8c3f4af
**Pattern:** Two-phase competition (generate → functional test)

## Hypothesis

Can Mobius agents design useful Claude Code skills? And can a second wave of agents validate whether those skills actually work?

## Setup

**Task:** Design a Claude Code skill for Mobius that saves developer time or improves the system. Output a complete SKILL.md with frontmatter and helper scripts.

**6 agents, 2 tracks:**

### Scouts (web research → adapt existing patterns)
| Slug | Philosophy | Tools |
|------|-----------|-------|
| `skill-scout-trending` | Find high-traction GitHub skills, adapt for agent swarms | WebSearch, WebFetch, Read, Grep, Glob, Bash |
| `skill-scout-ecosystem` | Research Claude Code ecosystem, find underutilized capabilities | WebSearch, WebFetch, Read, Grep, Glob, Bash |
| `skill-scout-devtools` | Find dev tool integrations, wrap multi-step workflows | WebSearch, WebFetch, Read, Grep, Glob, Bash |

### Smiths (analyze codebase → invent from scratch)
| Slug | Philosophy | Tools |
|------|-----------|-------|
| `skill-smith-gaps` | Identify workflow gaps, design skills to fill them | Read, Grep, Glob, Bash |
| `skill-smith-meta` | Close open feedback loops in the system | Read, Grep, Glob, Bash |
| `skill-smith-minimal` | Smallest possible skill that solves a real problem | Read, Grep, Glob, Bash |

All agents: Haiku model, spawned in parallel via subagents.

## Phase 1: Generation Results

| Agent | Skill Produced | Scope |
|-------|---------------|-------|
| Scout - Trending | `/mobius-experiment` | 850-line SKILL.md, 5 scripts. Reproducible A/B testing with statistical rigor. |
| Scout - Ecosystem | `/mobius-analyze` | 146-line SKILL.md, 4 scripts. Battle matrices, rock-paper-scissors detection. |
| Scout - DevTools | `/mobius-export` | SKILL.md + 2 scripts. YAML/JSON export/import for version control. |
| Smith - Gap Analyzer | `/mobius-insight` | 592-line SKILL.md, 5 scripts. Analytics with 4 modes (analyze, genealogy, trends, optimize). |
| Smith - Meta Improver | `/mobius-replay` | 202-line SKILL.md, 2 scripts. Match forensics and post-mortem analysis. |
| Smith - Minimalist | `/mobius-profile` | Short SKILL.md, 1 script (145 lines). Agent deep-dive with challenger recommendations. |

### Design Scores (Opus judge)

| Agent | Correctness | Quality | Completeness | Total |
|-------|------------|---------|-------------|-------|
| Scout - Trending | 6 | 4 | 8 | 18 |
| Scout - Ecosystem | 7 | 7 | 7 | 21 |
| Scout - DevTools | 8 | 7 | 7 | 22 |
| Smith - Gap Analyzer | 7 | 6 | 8 | 21 |
| Smith - Meta Improver | 8 | 8 | 7 | 23 |
| Smith - Minimalist | 9 | 9 | 7 | 25 |

## Phase 2: Functional Testing

A second wave of Haiku subagents attempted to run each skill's scripts against the live database.

| Skill | Pass/Fail | Functional Score | Key Findings |
|-------|-----------|-----------------|--------------|
| `/mobius-profile` | PASS | 9/10 | All features work. Edge cases handled. Tested against live DB with 40 agents. |
| `/mobius-export` | PASS | 9/10 | Flawless round-trip export→import. Zero data loss. All formats valid. |
| `/mobius-insight` | PASS | 9/10 | All 5 scripts work, valid JSON. Genealogy empty (no evolve runs yet) but correctly reports it. |
| `/mobius-analyze` | PASS | 8/10 | Full pipeline works. Unicode issue on Windows. RPS detection not actually implemented despite being promised. |
| `/mobius-experiment` | PASS | 8/10 | Scripts parse and run but `run_experiment.py` simulates results rather than calling real Mobius CLI. |
| `/mobius-replay` | PASS (bugs fixed) | 6/10 | 2 critical bugs: `json.loads` on plain UUID, f-string errors. Tester had to fix them. Missing promised features. |

## Combined Rankings

| Rank | Skill | Design | Functional | Combined |
|------|-------|--------|-----------|----------|
| 1 | `/mobius-profile` | 25 | 9 | 34 |
| 2 | `/mobius-export` | 22 | 9 | 31 |
| 3 | `/mobius-insight` | 21 | 9 | 30 |
| 4 | `/mobius-analyze` | 21 | 8 | 29 |
| 5 | `/mobius-replay` | 23 | 6 | 29 |
| 6 | `/mobius-experiment` | 18 | 8 | 26 |

## Findings

### What worked
- **Smiths dominated scouts.** All 3 codebase-analyzers outperformed web researchers. Having direct access to the code produced more relevant, testable skills.
- **Minimalism won.** Fewer lines = fewer bugs. The 145-line profile script worked perfectly; the 850-line experiment framework simulated instead of integrating.
- **Two-phase testing is essential.** Design scores and functional scores diverged significantly. `/mobius-replay` scored 2nd in design but last in functional testing (shipped with crashing bugs). You can't judge a skill by reading its SKILL.md.

### What didn't work
- **Scouts didn't leverage web research well.** Despite having WebSearch/WebFetch tools, the scouts produced skills that could have been designed without any web research. The trending scout produced the most over-engineered solution.
- **Haiku agents over-promise.** SKILL.md descriptions claimed features that the scripts didn't implement (RPS detection in analyze, recommendations in replay).

### Overlap discovered
- `/mobius-export` overlaps with existing `mobius agent export <slug>` CLI command
- `/mobius-insight` overlaps heavily with `mobius stats` + `mobius leaderboard`
- `/mobius-profile` overlaps with `mobius agent show` but adds challenger recommendations (genuine new value)

## Decisions

- **Kept:** `/mobius-profile` — fills a real gap (challenger recommendations not available elsewhere)
- **Removed:** The other 5 skill directories — overlap with existing CLI or not production-ready
- **Ideas preserved:** See `ideas.md` for concepts worth revisiting

## Meta: The Two-Phase Pattern

The most valuable outcome wasn't any individual skill — it was the **generate → test** competition pattern itself. This is the closest thing to automated experimentation on agent output quality:

1. Seed N agents with different philosophies
2. Run them on a generative task (produce code/artifacts)
3. Spawn a second wave of agents to functionally test the outputs
4. Score on both design quality AND working reality

This pattern should become a repeatable skill (`/mobius-forge` or similar).
