"""Typer CLI entrypoint for Mobius."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import typer
from rich.console import Console

from mobius.config import get_config

app = typer.Typer(
    name="mobius",
    help="Adversarial agent swarm orchestrator with multi-provider support.",
    no_args_is_help=True,
)
agent_app = typer.Typer(help="Manage agent definitions.")
app.add_typer(agent_app, name="agent")

console = Console()


def _setup_logging(verbose: bool = False) -> None:
    config = get_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(str(config.log_path)),
            logging.StreamHandler(sys.stderr) if verbose else logging.NullHandler(),
        ],
    )


def _get_components():
    """Initialize all components. Returns (config, conn, registry, tournament, memory, selector, swarm, judge_panel, orchestrator)."""
    from mobius.config import get_config
    from mobius.db import init_db
    from mobius.judge import JudgePanel
    from mobius.memory import Memory
    from mobius.orchestrator import Orchestrator
    from mobius.registry import Registry
    from mobius.selector import Selector
    from mobius.swarm import Swarm
    from mobius.tournament import Tournament

    config = get_config()
    conn, vec_available = init_db(config)
    registry = Registry(conn, config)
    tournament = Tournament(conn, config, registry)
    memory = Memory(conn, config, vec_available)
    selector = Selector(registry, memory, config)
    swarm = Swarm(config)
    judge_panel = JudgePanel(config)
    orchestrator = Orchestrator(config, selector, swarm, judge_panel, tournament, memory)
    return config, conn, registry, tournament, memory, selector, swarm, judge_panel, orchestrator


# --- Top-level commands ---


@app.command()
def init(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Initialize the Mobius database and directory structure."""
    _setup_logging(verbose)
    config = get_config()
    from mobius.db import init_db

    conn, vec_available = init_db(config)

    # Seed default agents
    from mobius.registry import Registry
    from mobius.seeds import DEFAULT_AGENTS

    registry = Registry(conn, config)
    seeded = 0
    for agent in DEFAULT_AGENTS:
        if not registry.get_agent_by_slug(agent.slug):
            registry.create_agent(agent)
            console.print(f"[green]Seeded: {agent.name} ({agent.slug})[/green]")
            seeded += 1

    conn.close()

    console.print(f"[green]Database initialized at {config.db_path}[/green]")
    if seeded:
        console.print(f"[green]{seeded} default agent(s) seeded[/green]")
    if vec_available:
        console.print("[green]sqlite-vec loaded — vector search enabled[/green]")
    else:
        console.print("[yellow]sqlite-vec not available — vector search disabled[/yellow]")
        console.print("[dim]Install with: pip install sqlite-vec[/dim]")


@app.command()
def run(
    task: str = typer.Argument(..., help="The task for agents to compete on"),
    n: int = typer.Option(None, "--agents", "-n", help="Number of competing agents"),
    no_ui: bool = typer.Option(False, "--no-ui", help="Disable live terminal UI"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run a competition: select agents, execute in parallel, judge outputs."""
    _setup_logging(verbose)
    config, conn, registry, tournament, memory, selector, swarm, judge_panel, orchestrator = _get_components()

    if n:
        config.swarm_size = n

    agent_count = registry.count_agents()
    if agent_count == 0:
        console.print("[red]No agents registered. Run 'mobius bootstrap' first.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Starting competition[/bold] ({agent_count} agents in pool, selecting best {n or config.swarm_size})")
    console.print(f"[dim]Task: {task[:100]}{'...' if len(task) > 100 else ''}[/dim]")
    console.print()

    # Preview which agents will be selected (the orchestrator does the real selection)
    preview_selected, strategy, memory_matches = selector.select(task, n=n)
    needs_new = getattr(selector, "needs_new_agent", False)
    console.print(f"[bold]Strategy: {strategy}[/bold] (memory matches: {len(memory_matches)})")
    if needs_new:
        console.print("[yellow]No strong contender — will attempt to create a new agent[/yellow]")
    for i, a in enumerate(preview_selected):
        label = "[dim](wildcard)[/dim]" if i == len(preview_selected) - 1 else ""
        console.print(f"  [cyan]{a.name}[/cyan] ({a.provider}/{a.model}) {label}")
    console.print()

    result = asyncio.run(orchestrator.run_competition(
        task, show_ui=not no_ui, working_dir=os.getcwd(),
    ))

    if result.verdict is None:
        console.print("[red]Competition voided — no successful outputs.[/red]")
        raise typer.Exit(1)

    from mobius.ui import print_verdict
    print_verdict(
        result.verdict,
        result.agents,
        {aid: r.output for aid, r in result.swarm_result.outputs.items() if r.success},
        result.judge_models,
    )

    # Export winner to .claude/agents/
    if result.winner and result.winner.provider == "anthropic":
        path = registry.export_to_claude_agents(result.winner)
        console.print(f"\n[dim]Winner exported to {path}[/dim]")

    conn.close()


@app.command()
def bootstrap(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Seed initial agents via the Agent Builder (Opus)."""
    _setup_logging(verbose)
    config, conn, registry, *_ = _get_components()[:3]
    from mobius.agent_builder import AgentBuilder

    existing = registry.count_agents()
    if existing > 0:
        console.print(f"[yellow]Registry already has {existing} agents.[/yellow]")
        if not typer.confirm("Add more agents?"):
            raise typer.Exit(0)

    builder = AgentBuilder(config)
    console.print("[bold]Bootstrapping agents via Opus...[/bold]")

    agents = asyncio.run(builder.bootstrap())
    for agent in agents:
        # Check for slug conflict
        if registry.get_agent_by_slug(agent.slug):
            console.print(f"[yellow]Skipping {agent.slug} — already exists[/yellow]")
            continue
        agent.is_champion = True  # First of their kind = champion
        registry.create_agent(agent)
        console.print(f"[green]Created: {agent.name} ({agent.provider}/{agent.model})[/green]")

    console.print(f"\n[bold green]Bootstrapped {len(agents)} agents.[/bold green]")
    conn.close()


@app.command()
def scout(
    path: str = typer.Argument(".", help="Path to codebase to analyze"),
    count: int = typer.Option(5, "--count", "-n", help="Number of agents to generate"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Analyze a codebase and generate specialized agents."""
    _setup_logging(verbose)
    config, conn, registry, *_ = _get_components()[:3]
    from mobius.agent_builder import AgentBuilder

    target = Path(path).resolve()
    if not target.exists():
        console.print(f"[red]Path not found: {target}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Scouting {target}...[/bold]")

    # Build a rich codebase summary by reading key files
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".egg-info"}
    skip_exts = {".pyc", ".lock", ".svg", ".png", ".jpg", ".woff", ".ttf", ".ico"}

    files = []
    for p in sorted(target.rglob("*")):
        if p.is_file() and not any(part in skip_dirs for part in p.relative_to(target).parts):
            if p.suffix not in skip_exts:
                files.append(str(p.relative_to(target)))

    console.print(f"[dim]Found {len(files)} files[/dim]")

    # Read key files for deep understanding
    key_file_patterns = [
        "README.md", "CLAUDE.md", "AGENTS.md",
        "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
        "requirements.txt", "Gemfile",
    ]
    key_contents: dict[str, str] = {}
    for pattern in key_file_patterns:
        fp = target / pattern
        if fp.exists():
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")[:3000]
                key_contents[pattern] = text
                console.print(f"[dim]  Read: {pattern} ({len(text)} chars)[/dim]")
            except Exception:
                pass

    # Read a sample of source files to understand patterns
    src_samples: dict[str, str] = {}
    src_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb"}
    for f in files:
        if Path(f).suffix in src_extensions and len(src_samples) < 5:
            fp = target / f
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")[:2000]
                src_samples[f] = text
                console.print(f"[dim]  Sampled: {f}[/dim]")
            except Exception:
                pass

    # Build the summary
    summary_parts = [f"# Codebase: {target.name}\n"]

    # File tree
    summary_parts.append(f"## File Structure ({len(files)} files)\n")
    summary_parts.append("\n".join(f"  {f}" for f in files[:150]))
    if len(files) > 150:
        summary_parts.append(f"\n  ... and {len(files) - 150} more files")

    # Key file contents
    for name, content in key_contents.items():
        summary_parts.append(f"\n## {name}\n```\n{content}\n```")

    # Source samples
    for name, content in src_samples.items():
        summary_parts.append(f"\n## Sample: {name}\n```\n{content[:1500]}\n```")

    summary = "\n".join(summary_parts)
    console.print(f"[dim]Summary: {len(summary)} chars[/dim]")

    builder = AgentBuilder(config)
    console.print(f"[bold]Generating {count} specialized agents via Opus...[/bold]")
    agents = asyncio.run(builder.scout(summary, count=count))

    for agent in agents:
        if registry.get_agent_by_slug(agent.slug):
            console.print(f"[yellow]Skipping {agent.slug} — already exists[/yellow]")
            continue
        agent.is_champion = True
        registry.create_agent(agent)
        console.print(f"[green]Created: {agent.name} ({agent.provider}/{agent.model})[/green]")
        console.print(f"[dim]  {agent.description}[/dim]")
        console.print(f"[dim]  specs={agent.specializations}[/dim]")

    console.print(f"\n[bold green]Scout created {len(agents)} agents for {target.name}.[/bold green]")
    conn.close()


@app.command()
def evolve(
    specialization: str = typer.Argument(..., help="Specialization to evolve"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Trigger agent builder refinement for a specialization."""
    _setup_logging(verbose)
    config, conn, registry, tournament, *_ = _get_components()[:4]
    from mobius.agent_builder import AgentBuilder

    champions = registry.get_champions(specialization=specialization)
    if not champions:
        console.print(f"[red]No champions for '{specialization}'. Run more competitions first.[/red]")
        raise typer.Exit(1)

    builder = AgentBuilder(config)
    for champ in champions:
        # Gather recent judge feedback from losses
        matches = tournament.get_agent_matches(champ.id, limit=10)
        losses = [m for m in matches if m.winner_id != champ.id and not m.voided]

        if not losses:
            console.print(f"[yellow]{champ.name} has no recent losses — nothing to improve.[/yellow]")
            continue

        feedback = "\n\n".join(
            f"Task: {m.task_description[:100]}\nJudge: {m.judge_reasoning[:200]}"
            for m in losses[:5]
        )

        console.print(f"[bold]Evolving {champ.name} based on {len(losses)} losses...[/bold]")
        improved = asyncio.run(builder.refine_agent(champ, feedback))

        if improved:
            if registry.get_agent_by_slug(improved.slug):
                improved.slug = f"{improved.slug}-{improved.id[:6]}"
            registry.create_agent(improved)
            console.print(f"[green]Created challenger: {improved.name} (gen {improved.generation})[/green]")
        else:
            console.print(f"[red]Failed to create improved version of {champ.name}[/red]")

    conn.close()


@app.command()
def leaderboard(
    specialization: str = typer.Option(None, "--spec", "-s", help="Filter by specialization"),
    limit: int = typer.Option(20, "--limit", "-n"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show agent Elo rankings."""
    _setup_logging(verbose)
    config, conn, registry, tournament, *_ = _get_components()[:4]

    board = tournament.get_leaderboard(specialization=specialization, limit=limit)
    if not board:
        console.print("[yellow]No agents yet. Run 'mobius bootstrap' to get started.[/yellow]")
        raise typer.Exit(0)

    from mobius.ui import print_leaderboard
    print_leaderboard(board)
    conn.close()


@app.command()
def explain(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show judge reasoning and winner lineage for the last match."""
    _setup_logging(verbose)
    config, conn, registry, tournament, *_ = _get_components()[:4]

    matches = tournament.get_recent_matches(limit=1)
    if not matches:
        console.print("[yellow]No matches yet.[/yellow]")
        raise typer.Exit(0)

    match = matches[0]
    console.print(f"[bold]Match {match.id[:8]}[/bold]")
    console.print(f"Task: {match.task_description[:200]}")
    console.print(f"Judges: {', '.join(match.judge_models)}")
    console.print(f"Voided: {match.voided}")
    console.print()

    if match.winner_id:
        winner = registry.get_agent(match.winner_id)
        if winner:
            console.print(f"[green bold]Winner: {winner.name}[/green bold]")
            console.print(f"  Provider: {winner.provider}/{winner.model}")
            console.print(f"  Elo: {winner.elo_rating:.0f}")
            console.print(f"  Generation: {winner.generation}")
            if winner.parent_id:
                parent = registry.get_agent(winner.parent_id)
                if parent:
                    console.print(f"  Parent: {parent.name} (gen {parent.generation})")
            console.print(f"  Specializations: {', '.join(winner.specializations)}")

    console.print()
    console.print("[bold]Scores:[/bold]")
    for agent_id, score in sorted(match.scores.items(), key=lambda x: x[1], reverse=True):
        agent = registry.get_agent(agent_id)
        name = agent.name if agent else agent_id[:8]
        marker = " [green]WINNER[/green]" if agent_id == match.winner_id else ""
        console.print(f"  {name}: {score:.1f}{marker}")

    if match.judge_reasoning:
        console.print()
        console.print("[bold]Judge Reasoning:[/bold]")
        console.print(match.judge_reasoning)

    conn.close()


@app.command()
def stats(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Show overall Mobius statistics."""
    _setup_logging(verbose)
    config, conn, registry, tournament, memory, *_ = _get_components()[:5]

    console.print("[bold]Mobius Statistics[/bold]")
    console.print(f"  Agents:   {registry.count_agents()}")
    console.print(f"  Champions: {len(registry.get_champions())}")
    console.print(f"  Matches:  {tournament.total_matches()}")
    console.print(f"  Memories: {memory.count()}")
    console.print(f"  DB path:  {config.db_path}")

    conn.close()


@app.command(name="loop")
def run_loop(
    rounds: int = typer.Option(10, "--rounds", "-r", help="Number of competition rounds"),
    tasks_file: str = typer.Option(None, "--tasks", "-t", help="File with tasks (one per line)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run multiple competitions in a self-improvement loop."""
    _setup_logging(verbose)
    config, conn, registry, tournament, memory, selector, swarm, judge_panel, orchestrator = _get_components()

    if registry.count_agents() == 0:
        console.print("[red]No agents. Run 'mobius bootstrap' first.[/red]")
        raise typer.Exit(1)

    # Load tasks
    tasks: list[str] = []
    if tasks_file:
        import json
        raw = Path(tasks_file).read_text().strip()
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                # JSON array: extract "task" field from objects, or use strings directly
                tasks = [
                    item["task"] if isinstance(item, dict) and "task" in item else str(item)
                    for item in loaded
                ]
            else:
                tasks = raw.splitlines()
        except (json.JSONDecodeError, ValueError):
            tasks = raw.splitlines()
    else:
        # Default benchmark tasks
        tasks = [
            "Write a Python function to find the longest common subsequence of two strings",
            "Refactor this code to use async/await instead of callbacks",
            "Write unit tests for a REST API endpoint that handles user registration",
            "Debug this function that incorrectly handles edge cases with empty input",
            "Write a Python class that implements an LRU cache with O(1) operations",
        ]

    console.print(f"[bold]Running {rounds} rounds with {len(tasks)} task templates[/bold]")

    import itertools
    task_cycle = itertools.cycle(tasks)

    for i in range(rounds):
        task = next(task_cycle)
        console.print(f"\n[bold]--- Round {i+1}/{rounds} ---[/bold]")
        console.print(f"[dim]Task: {task[:80]}...[/dim]")

        try:
            result = asyncio.run(orchestrator.run_competition(
                task, show_ui=False, working_dir=os.getcwd(),
            ))
            if result.winner:
                console.print(f"[green]Winner: {result.winner.name} (Elo: {result.winner.elo_rating:.0f})[/green]")
            else:
                console.print("[yellow]Match voided[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            continue

        # Evolution check
        if (i + 1) % config.evolve_every_n_matches == 0:
            console.print("[bold blue]Triggering evolution check...[/bold blue]")
            from mobius.agent_builder import AgentBuilder
            builder = AgentBuilder(config)
            agents = registry.list_agents()
            for agent in agents:
                rate = tournament.get_agent_recent_win_rate(agent.id, window=config.underperformer_window)
                if rate < config.underperformer_win_rate and agent.total_matches >= 5:
                    console.print(f"[yellow]Evolving underperformer: {agent.name} (win rate: {rate:.0%})[/yellow]")
                    # Get feedback from losses
                    matches = tournament.get_agent_matches(agent.id, limit=5)
                    losses = [m for m in matches if m.winner_id != agent.id and not m.voided]
                    feedback = "\n".join(m.judge_reasoning[:200] for m in losses[:3])
                    if feedback:
                        improved = asyncio.run(builder.refine_agent(agent, feedback))
                        if improved and not registry.get_agent_by_slug(improved.slug):
                            registry.create_agent(improved)
                            console.print(f"[green]Created challenger: {improved.name}[/green]")

    console.print(f"\n[bold green]Loop complete. {rounds} rounds executed.[/bold green]")
    conn.close()


@app.command()
def train(
    challenge: str = typer.Argument(..., help="The challenge to train agents on"),
    rounds: int = typer.Option(5, "--rounds", "-r", help="Training rounds"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Train agents on a single challenge through iterative competition and refinement.

    Unlike 'loop' which cycles through many tasks, 'train' hammers one challenge
    repeatedly. After each round, losers are refined based on judge feedback and
    re-enter the next round. The output is battle-tested agents, not just answers.
    """
    _setup_logging(verbose)
    config, conn, registry, tournament, memory, selector, swarm, judge_panel, orchestrator = _get_components()

    if registry.count_agents() == 0:
        console.print("[red]No agents. Run 'mobius bootstrap' first.[/red]")
        raise typer.Exit(1)

    from mobius.agent_builder import AgentBuilder
    builder = AgentBuilder(config)

    console.print(f"[bold]Training on challenge:[/bold] {challenge}")
    console.print(f"[bold]Rounds:[/bold] {rounds}")
    console.print()

    generation_log: list[dict] = []  # track evolution per round

    for i in range(rounds):
        console.print(f"\n[bold]{'='*60}[/bold]")
        console.print(f"[bold]  Round {i+1}/{rounds}[/bold]")
        console.print(f"[bold]{'='*60}[/bold]")

        # Run competition
        try:
            result = asyncio.run(orchestrator.run_competition(
                challenge, show_ui=True, working_dir=os.getcwd(),
            ))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            continue

        if result.verdict is None:
            console.print("[yellow]Match voided — no successful outputs.[/yellow]")
            continue

        # Show result
        winner = result.winner
        winner_name = winner.name if winner else "Unknown"
        console.print(f"\n[green]Winner: {winner_name}[/green]")
        if result.verdict.reasoning:
            console.print(f"[dim]Judge: {result.verdict.reasoning[:200]}...[/dim]")

        round_info = {
            "round": i + 1,
            "winner": winner_name,
            "winner_gen": winner.generation if winner else 0,
            "agents_evolved": [],
        }

        # Evolve losers immediately — every round, not every N matches
        losers = [
            (aid, result.agents[aid])
            for aid in result.swarm_result.successful_outputs
            if aid != result.verdict.winner and aid in result.agents
        ]

        if losers and result.verdict.reasoning:
            console.print(f"\n[blue]Refining {len(losers)} losing agent(s)...[/blue]")

            for loser_id, loser in losers:
                loser_score = result.verdict.scores.get(loser_id, 0)
                loser_output_preview = result.swarm_result.outputs[loser_id].output[:300]

                # Build targeted feedback: what the judge said + how this agent's output compared
                feedback = (
                    f"Task: {challenge}\n\n"
                    f"Your output scored {loser_score:.1f} and lost.\n\n"
                    f"Your output began:\n{loser_output_preview}\n\n"
                    f"Judge reasoning:\n{result.verdict.reasoning}"
                )

                try:
                    improved = asyncio.run(builder.refine_agent(loser, feedback))
                except Exception as e:
                    console.print(f"  [red]Failed to refine {loser.name}: {e}[/red]")
                    continue

                if improved:
                    # Deduplicate slug
                    if registry.get_agent_by_slug(improved.slug):
                        improved.slug = f"{improved.slug}-{improved.id[:6]}"
                    registry.create_agent(improved)
                    round_info["agents_evolved"].append(improved.name)
                    console.print(
                        f"  [green]{loser.name}[/green] → [cyan]{improved.name}[/cyan] "
                        f"(gen {improved.generation}, parent={loser.slug})"
                    )

        generation_log.append(round_info)

    # --- Summary ---
    console.print(f"\n\n[bold]{'='*60}[/bold]")
    console.print(f"[bold]  Training Complete — {rounds} rounds[/bold]")
    console.print(f"[bold]{'='*60}[/bold]")
    console.print(f"\n[bold]Challenge:[/bold] {challenge}\n")

    from rich.table import Table
    table = Table(title="Round-by-Round Evolution")
    table.add_column("Round", style="dim", width=6)
    table.add_column("Winner", style="green")
    table.add_column("Gen", style="yellow", width=5)
    table.add_column("Agents Evolved", style="cyan")

    for entry in generation_log:
        evolved = ", ".join(entry["agents_evolved"]) if entry["agents_evolved"] else "-"
        table.add_row(
            str(entry["round"]),
            entry["winner"],
            str(entry["winner_gen"]),
            evolved,
        )
    console.print(table)

    # Show top agents that emerged
    console.print("\n[bold]Top agents after training:[/bold]")
    board = tournament.get_leaderboard(limit=10)
    for entry in board[:5]:
        console.print(
            f"  [cyan]{entry['name']}[/cyan] "
            f"(Elo: {entry['elo']:.0f}, gen {entry.get('generation', '?')}, "
            f"win rate: {entry['win_rate']:.0%})"
        )

    conn.close()


# --- Agent subcommands ---


@agent_app.command("list")
def agent_list(
    spec: str = typer.Option(None, "--spec", "-s"),
    provider: str = typer.Option(None, "--provider", "-p"),
    champions: bool = typer.Option(False, "--champions", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List registered agents."""
    _setup_logging(verbose)
    config, conn, registry, *_ = _get_components()[:3]

    agents = registry.list_agents(
        specialization=spec,
        champions_only=champions,
        provider=provider,
    )

    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        raise typer.Exit(0)

    from rich.table import Table
    table = Table(title=f"Agents ({len(agents)})")
    table.add_column("Slug", style="cyan")
    table.add_column("Name")
    table.add_column("Provider", style="blue")
    table.add_column("Model", style="magenta")
    table.add_column("Elo", justify="right")
    table.add_column("W/L", justify="right")
    table.add_column("Gen", justify="right")
    table.add_column("Champ", justify="center")
    table.add_column("Specs", style="dim")

    for a in agents:
        champ = "[green]Y[/green]" if a.is_champion else ""
        wins = int(a.win_rate * a.total_matches)
        losses = a.total_matches - wins
        table.add_row(
            a.slug,
            a.name,
            a.provider,
            a.model.split("/")[-1][:20],
            f"{a.elo_rating:.0f}",
            f"{wins}/{losses}",
            str(a.generation),
            champ,
            ", ".join(a.specializations),
        )

    console.print(table)
    conn.close()


@agent_app.command("show")
def agent_show(
    slug: str = typer.Argument(..., help="Agent slug"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show details of a specific agent."""
    _setup_logging(verbose)
    config, conn, registry, *_ = _get_components()[:3]

    agent = registry.get_agent_by_slug(slug)
    if not agent:
        console.print(f"[red]Agent '{slug}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]{agent.name}[/bold] ({agent.slug})")
    console.print(f"  ID: {agent.id}")
    console.print(f"  Provider: {agent.provider}")
    console.print(f"  Model: {agent.model}")
    console.print(f"  Tools: {', '.join(agent.tools)}")
    console.print(f"  Max turns: {agent.max_turns}")
    console.print(f"  Specializations: {', '.join(agent.specializations)}")
    console.print(f"  Generation: {agent.generation}")
    console.print(f"  Parent: {agent.parent_id or 'None'}")
    console.print(f"  Champion: {agent.is_champion}")
    console.print(f"  Elo: {agent.elo_rating:.0f}")
    console.print(f"  Win rate: {agent.win_rate:.0%}")
    console.print(f"  Total matches: {agent.total_matches}")
    console.print(f"  Created: {agent.created_at}")
    console.print()
    console.print("[bold]System Prompt:[/bold]")
    console.print(agent.system_prompt)

    conn.close()


@agent_app.command("export")
def agent_export(
    slug: str = typer.Argument(..., help="Agent slug to export"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Export an agent as a .claude/agents/ markdown file."""
    _setup_logging(verbose)
    config, conn, registry, *_ = _get_components()[:3]

    agent = registry.get_agent_by_slug(slug)
    if not agent:
        console.print(f"[red]Agent '{slug}' not found.[/red]")
        raise typer.Exit(1)

    path = registry.export_to_claude_agents(agent)
    console.print(f"[green]Exported to {path}[/green]")
    conn.close()


if __name__ == "__main__":
    app()
