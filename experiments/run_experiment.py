"""Run a multi-round Mobius experiment with metrics tracking.

Usage:
    python experiments/run_experiment.py                    # 3-round quick experiment
    python experiments/run_experiment.py --rounds 50        # 50 rounds
    python experiments/run_experiment.py --hours 8          # run for 8 hours
    python experiments/run_experiment.py --tasks tasks.txt  # custom task file
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mobius.config import get_config
from mobius.db import init_db, vec_to_blob
from mobius.embedder import embed
from mobius.judge import JudgePanel
from mobius.memory import Memory
from mobius.metrics import ExperimentReport, generate_report, print_report
from mobius.models import MatchRecord, MemoryEntry
from mobius.registry import Registry
from mobius.swarm import Swarm
from mobius.tournament import Tournament
from mobius.ui import SwarmUI, print_verdict, console

# Default experiment tasks — mix of difficulties and domains
DEFAULT_TASKS = [
    # Round 1: Straightforward coding
    "Write a Python function called `fibonacci_memo` that returns the nth Fibonacci number using memoization. Include type hints, handle edge cases (n < 0, n = 0), and show example usage.",

    # Round 2: Design + architecture
    "Write a Python class called `EventBus` that implements the publish-subscribe pattern. It should support: subscribing to events by name, publishing events with data, unsubscribing, and wildcard subscriptions (e.g., 'user.*' matches 'user.login' and 'user.logout'). Include type hints and example usage.",

    # Round 3: Complex algorithm
    "Write a Python function called `find_shortest_path` that implements Dijkstra's algorithm to find the shortest path in a weighted graph. The graph should be represented as an adjacency dict (e.g., {'A': [('B', 5), ('C', 2)]}). Return both the shortest distance and the path. Handle edge cases like disconnected nodes. Include type hints and example usage.",
]

LONG_RUNNING_TASKS = [
    "Write a Python decorator called `retry` that retries a function up to N times with exponential backoff. Support configurable max_retries, base_delay, and specific exception types to catch. Include type hints and tests.",
    "Write a Python function that validates email addresses using regex. It should handle common edge cases (subdomains, plus addressing, international domains). Return a named tuple with (is_valid, local_part, domain). Include comprehensive test cases.",
    "Write a Python class called `RateLimiter` that implements a token bucket rate limiter. Support configurable rate (tokens per second) and burst size. Thread-safe. Include type hints and usage examples.",
    "Write a Python function called `flatten_json` that takes a nested JSON/dict structure and returns a flat dict with dot-notation keys (e.g., {'a': {'b': 1}} becomes {'a.b': 1}). Handle arrays, None values, and circular references. Include type hints.",
    "Write a Python async context manager called `timeout` that raises TimeoutError if the wrapped code doesn't complete within N seconds. Include type hints and example usage with asyncio.",
    "Write a Python function called `diff_dicts` that compares two dictionaries recursively and returns a structured diff showing added, removed, and changed keys with their old/new values. Handle nested dicts and lists. Include type hints.",
    "Write a Python class called `CircuitBreaker` implementing the circuit breaker pattern. Support CLOSED, OPEN, and HALF_OPEN states. Configurable failure threshold, recovery timeout, and success threshold. Include type hints and example usage.",
    "Write a Python function to parse and evaluate simple mathematical expressions (addition, subtraction, multiplication, division, parentheses) without using eval(). Handle operator precedence correctly. Include type hints and test cases.",
    "Design a landing page for a developer tools startup called 'CodePilot' that offers AI-powered code review. Include hero section, features, testimonials, and pricing. Dark theme with green accents. Output a single HTML file with Tailwind CSS.",
    "Design a dashboard UI for a fitness tracking app. Show a weekly activity summary with progress bars, a workout calendar, and daily stats cards. Use a clean, modern design. Output a single HTML file with Tailwind CSS.",
]


async def run_single_round(
    task: str,
    round_num: int,
    total_rounds: int,
    registry: Registry,
    swarm: Swarm,
    judge_panel: JudgePanel,
    tournament: Tournament,
    memory: Memory,
    config,
    skip_providers: list[str] | None = None,
) -> bool:
    """Run a single competition round. Returns True if successful."""
    console.print(f"\n[bold blue]{'='*60}[/bold blue]")
    console.print(f"[bold]Round {round_num}/{total_rounds}[/bold] — {datetime.now().strftime('%H:%M:%S')}")
    console.print(f"[dim]Task: {task[:100]}{'...' if len(task) > 100 else ''}[/dim]")
    console.print(f"[bold blue]{'='*60}[/bold blue]")

    # Select agents (skip unavailable providers)
    all_agents = registry.list_agents()
    if skip_providers:
        agents = [a for a in all_agents if a.provider not in skip_providers]
    else:
        agents = all_agents

    if len(agents) < 2:
        console.print("[red]Not enough agents to compete.[/red]")
        return False

    # Limit to swarm_size
    agents = agents[:config.swarm_size]

    agent_map = {a.id: a for a in agents}
    console.print(f"[dim]Competitors: {', '.join(a.name for a in agents)}[/dim]")

    # Run swarm
    ui = SwarmUI()
    for a in agents:
        ui.agents[a.id] = a
        ui.statuses[a.id] = "waiting"

    live = ui.start()
    try:
        with live:
            swarm_result = await swarm.run(
                task=task, agents=agents,
                on_start=ui.on_start, on_complete=ui.on_complete,
            )
    finally:
        ui.stop()

    successful = swarm_result.successful_outputs
    console.print(f"\n[dim]{len(successful)}/{len(agents)} agents produced output[/dim]")

    if len(successful) < 2:
        # Record voided match
        match = MatchRecord(
            task_description=task,
            competitor_ids=[a.id for a in agents],
            voided=True,
        )
        tournament.record_match(match)
        console.print("[yellow]Round voided — not enough outputs to judge.[/yellow]")
        return False

    # Judge
    outputs_text = {aid: r.output for aid, r in successful.items()}
    verdict, judge_models = await judge_panel.evaluate(task, outputs_text)

    if not verdict:
        match = MatchRecord(
            task_description=task,
            competitor_ids=[a.id for a in agents],
            voided=True,
        )
        tournament.record_match(match)
        console.print("[yellow]Round voided — judge failed.[/yellow]")
        return False

    # Record match
    task_vec = embed(task, config)
    match = MatchRecord(
        task_description=task,
        task_embedding=vec_to_blob(task_vec),
        competitor_ids=[a.id for a in agents],
        outputs=outputs_text,
        judge_models=judge_models,
        judge_reasoning=verdict.reasoning,
        winner_id=verdict.winner,
        scores=verdict.scores,
    )
    tournament.record_match(match)

    # Store memory
    if verdict.winner:
        memory.store(MemoryEntry(
            task_embedding=vec_to_blob(task_vec),
            task_text=task,
            winning_agent_id=verdict.winner,
            score=max(verdict.scores.values()) if verdict.scores else 0,
        ))

    # Print result
    winner = agent_map.get(verdict.winner)
    winning_score = max(verdict.scores.values()) if verdict.scores else 0
    if winner:
        console.print(f"[green bold]Winner: {winner.name}[/green bold] ({winner.provider}/{winner.model}) — Score: {winning_score:.0f}/30")
    console.print(f"[dim]Judge: {', '.join(judge_models)}[/dim]")

    return True


async def run_experiment(
    tasks: list[str],
    rounds: int | None = None,
    hours: float | None = None,
    skip_providers: list[str] | None = None,
):
    """Run a full experiment."""
    config = get_config()
    config.judge_models = [
        {"provider": "google", "model": "gemini-2.5-flash"},
    ]

    conn, vec_available = init_db(config)
    registry = Registry(conn, config)
    tournament = Tournament(conn, config, registry)
    memory = Memory(conn, config, vec_available)
    swarm = Swarm(config)
    judge_panel = JudgePanel(config)

    agent_count = registry.count_agents()
    if agent_count == 0:
        console.print("[red]No agents! Run 'mobius bootstrap' or '/mobius-seed' first.[/red]")
        return

    console.print(f"\n[bold]Starting Mobius Experiment[/bold]")
    console.print(f"  Agents in pool: {agent_count}")
    console.print(f"  Tasks: {len(tasks)}")
    if rounds:
        console.print(f"  Rounds: {rounds}")
    if hours:
        console.print(f"  Duration: {hours}h")
    if skip_providers:
        console.print(f"  Skipping providers: {', '.join(skip_providers)}")

    start_time = time.time()
    round_num = 0
    task_idx = 0

    # Determine stop condition
    if hours:
        end_time = start_time + hours * 3600
        total_rounds = 999999  # effectively unlimited
    else:
        total_rounds = rounds or len(tasks)
        end_time = None

    while round_num < total_rounds:
        if end_time and time.time() > end_time:
            console.print(f"\n[bold]Time limit reached ({hours}h).[/bold]")
            break

        task = tasks[task_idx % len(tasks)]
        task_idx += 1
        round_num += 1

        try:
            await run_single_round(
                task=task,
                round_num=round_num,
                total_rounds=total_rounds if total_rounds < 999999 else round_num,
                registry=registry,
                swarm=swarm,
                judge_panel=judge_panel,
                tournament=tournament,
                memory=memory,
                config=config,
                skip_providers=skip_providers,
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted! Saving progress...[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Round {round_num} error: {e}[/red]")
            continue

    # Generate and print report
    elapsed = time.time() - start_time
    report = generate_report(conn, config, last_n=round_num)
    print_report(report, title=f"Experiment Complete ({elapsed/60:.1f} min)")

    # Print final leaderboard
    console.print()
    from mobius.ui import print_leaderboard
    board = tournament.get_leaderboard()
    print_leaderboard(board)

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Run a Mobius experiment")
    parser.add_argument("--rounds", "-r", type=int, help="Number of rounds")
    parser.add_argument("--hours", type=float, help="Run for N hours")
    parser.add_argument("--tasks", "-t", type=str, help="File with tasks (one per line)")
    parser.add_argument("--skip", type=str, help="Comma-separated providers to skip (e.g., 'anthropic')")
    args = parser.parse_args()

    if args.tasks:
        tasks = Path(args.tasks).read_text().strip().splitlines()
        tasks = [t.strip() for t in tasks if t.strip()]
    elif args.hours:
        tasks = DEFAULT_TASKS + LONG_RUNNING_TASKS
    else:
        tasks = DEFAULT_TASKS

    skip = args.skip.split(",") if args.skip else None

    asyncio.run(run_experiment(
        tasks=tasks,
        rounds=args.rounds,
        hours=args.hours,
        skip_providers=skip,
    ))


if __name__ == "__main__":
    main()
