"""Research Challenge: Find the best GitHub projects for a topic.

Uses agents from the registry — no hardcoded prompts.
Seed researcher agents first via: mobius bootstrap, /mobius-seed, or the CLI.

Usage:
    python experiments/research_challenge.py swarms
    python experiments/research_challenge.py "agent orchestration"
    python experiments/research_challenge.py "vector database" --spec research
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mobius.config import get_config
from mobius.db import init_db, vec_to_blob
from mobius.embedder import embed
from mobius.judge import JudgePanel
from mobius.memory import Memory
from mobius.models import MatchRecord, MemoryEntry
from mobius.registry import Registry
from mobius.swarm import Swarm
from mobius.tournament import Tournament
from mobius.ui import SwarmUI, console, print_verdict


def fetch_github_data(query: str, max_results: int = 30) -> list[dict]:
    """Fetch real GitHub search results using the gh CLI."""
    searches = [
        f'gh search repos "{query}" --sort stars --limit 20 --json fullName,description,stargazersCount,language,updatedAt,url',
        f'gh search repos "{query} framework" --sort stars --limit 15 --json fullName,description,stargazersCount,language,updatedAt,url',
        f'gh search repos "{query} multi-agent" --sort stars --limit 15 --json fullName,description,stargazersCount,language,updatedAt,url',
    ]
    all_repos = []
    seen = set()
    for cmd in searches:
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=15, encoding="utf-8", errors="replace",
            )
            if r.returncode == 0:
                for repo in json.loads(r.stdout):
                    if repo["fullName"] not in seen:
                        seen.add(repo["fullName"])
                        all_repos.append(repo)
        except Exception:
            pass

    all_repos.sort(key=lambda x: x.get("stargazersCount", 0), reverse=True)
    return all_repos[:max_results]


def format_gh_context(repos: list[dict]) -> str:
    """Format GitHub data as readable context for agents."""
    lines = []
    for i, r in enumerate(repos):
        desc = (r.get("description") or "No description")[:150]
        lines.append(
            f"{i+1}. **{r['fullName']}** ({r.get('stargazersCount', 0)} stars, {r.get('language') or '?'})\n"
            f"   {desc}\n"
            f"   Updated: {r.get('updatedAt', '?')[:10]} | {r['url']}\n"
        )
    return "\n".join(lines)


async def run_research_challenge(topic: str, specialization: str = "research"):
    """Run the research challenge using agents from the registry."""
    config = get_config()
    config.judge_models = [{"provider": "google", "model": "gemini-2.5-flash"}]
    config.agent_timeout_seconds = 180

    conn, vec_available = init_db(config)
    registry = Registry(conn, config)
    tournament = Tournament(conn, config, registry)
    memory = Memory(conn, config, vec_available)
    swarm = Swarm(config)
    judge_panel = JudgePanel(config)

    # Pull agents from registry — NO hardcoded definitions
    agents = registry.list_agents(specialization=specialization)

    if len(agents) < 2:
        console.print(f"[red]Only {len(agents)} agents with specialization '{specialization}'.[/red]")
        console.print("[yellow]Seed researcher agents first:[/yellow]")
        console.print("  mobius bootstrap")
        console.print("  /mobius-seed research")
        console.print(f"  Or create agents with specialization: {specialization}")
        conn.close()
        return

    # Fetch real GitHub data
    console.print(f"\n[bold]Fetching GitHub data for: {topic}[/bold]")
    repos = fetch_github_data(topic)
    console.print(f"[dim]Found {len(repos)} repos[/dim]\n")

    gh_context = format_gh_context(repos)

    console.print(f"[bold]Research Challenge: {len(agents)} agents competing[/bold]")
    for a in agents:
        console.print(f"  {a.name} ({a.provider}/{a.model})")

    # Build task — the agents' system_prompts (from the DB) define their approach
    task = (
        f'Research Challenge: Find and recommend the best GitHub projects related to "{topic}".\n\n'
        f"Here are real GitHub search results:\n\n"
        f"{gh_context}\n\n"
        f"Analyze these results. Filter out irrelevant repos. "
        f"Identify the best projects and explain why. Be specific and opinionated."
    )

    # Run swarm
    agent_map = {a.id: a for a in agents}
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
    console.print(f"\n{len(successful)}/{len(agents)} agents completed")

    # Save outputs
    for aid, r in successful.items():
        agent = agent_map[aid]
        filename = f"data/research-{agent.slug}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# Research by {agent.name}\n")
            f.write(f"Provider: {agent.provider}/{agent.model}\n")
            f.write(f"Topic: {topic}\n\n---\n\n")
            f.write(r.output)
        console.print(f"[dim]Saved: {filename}[/dim]")

    if len(successful) < 2:
        console.print("[red]Not enough outputs to judge[/red]")
        conn.close()
        return

    # Judge
    outputs_text = {aid: r.output for aid, r in successful.items()}
    verdict, judge_models = await judge_panel.evaluate(task, outputs_text)

    if verdict:
        task_vec = embed(f"Research: best GitHub projects for {topic}", config)
        match = MatchRecord(
            task_description=f'Research: best GitHub projects for "{topic}"',
            task_embedding=vec_to_blob(task_vec),
            competitor_ids=[a.id for a in agents],
            outputs=outputs_text,
            judge_models=judge_models,
            judge_reasoning=verdict.reasoning,
            winner_id=verdict.winner,
            scores=verdict.scores,
        )
        tournament.record_match(match)

        if verdict.winner:
            memory.store(MemoryEntry(
                task_embedding=vec_to_blob(task_vec),
                task_text=f"Research: {topic}",
                winning_agent_id=verdict.winner,
                score=max(verdict.scores.values()) if verdict.scores else 0,
            ))

        print_verdict(verdict, agent_map, outputs_text, judge_models)

        winner = agent_map.get(verdict.winner)
        if winner:
            console.print(f"\n[bold green]Best Researcher: {winner.name}[/bold green]")
            console.print(f"  data/research-{winner.slug}.md")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a research challenge")
    parser.add_argument("topic", nargs="?", default="swarms", help="Topic to research")
    parser.add_argument("--spec", default="research", help="Agent specialization to filter by")
    args = parser.parse_args()

    asyncio.run(run_research_challenge(args.topic, args.spec))
