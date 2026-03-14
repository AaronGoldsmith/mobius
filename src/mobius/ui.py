"""Rich Live terminal UI for swarm progress and results."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mobius.models import AgentRecord, JudgeVerdict
from mobius.providers.base import ProviderResult

console = Console()


class SwarmUI:
    """Live terminal display during swarm execution."""

    def __init__(self):
        self.agents: dict[str, AgentRecord] = {}
        self.statuses: dict[str, str] = {}  # agent_id -> status
        self.results: dict[str, ProviderResult] = {}
        self._live: Live | None = None

    def _build_table(self) -> Table:
        table = Table(title="Swarm Competition", expand=True)
        table.add_column("Agent", style="cyan", min_width=20)
        table.add_column("Provider", style="blue", min_width=10)
        table.add_column("Model", style="magenta", min_width=15)
        table.add_column("Status", min_width=15)
        table.add_column("Preview", max_width=50)

        for agent_id, agent in self.agents.items():
            status = self.statuses.get(agent_id, "waiting")
            result = self.results.get(agent_id)

            if status == "running":
                status_text = Text("running...", style="yellow")
            elif status == "done" and result and result.success:
                status_text = Text("completed", style="green")
            elif status == "done":
                status_text = Text(f"failed: {result.error[:30] if result and result.error else 'unknown'}", style="red")
            else:
                status_text = Text("waiting", style="dim")

            preview = ""
            if result and result.success:
                preview = result.output[:80].replace("\n", " ") + "..."

            table.add_row(
                agent.name,
                agent.provider,
                agent.model.split("/")[-1][:20],
                status_text,
                preview,
            )

        return table

    def on_start(self, agent: AgentRecord) -> None:
        """Called when an agent starts executing."""
        self.agents[agent.id] = agent
        self.statuses[agent.id] = "running"
        if self._live:
            self._live.update(self._build_table())

    def on_complete(self, agent: AgentRecord, result: ProviderResult) -> None:
        """Called when an agent finishes."""
        self.statuses[agent.id] = "done"
        self.results[agent.id] = result
        if self._live:
            self._live.update(self._build_table())

    def start(self) -> Live:
        """Start the live display."""
        self._live = Live(self._build_table(), console=console, refresh_per_second=4)
        return self._live

    def stop(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()
            self._live = None


def print_verdict(
    verdict: JudgeVerdict,
    agents: dict[str, AgentRecord],
    outputs: dict[str, str],
    judge_models: list[str],
) -> None:
    """Print the judge verdict with Rich formatting."""
    console.print()
    console.print(Panel("[bold]Judge Panel Results[/bold]", style="blue"))

    # Judge models used
    console.print(f"[dim]Judges: {', '.join(judge_models)}[/dim]")
    console.print()

    # Scores table
    table = Table(title="Scores")
    table.add_column("Agent", style="cyan")
    table.add_column("Provider", style="blue")
    table.add_column("Score", style="yellow", justify="right")
    table.add_column("Winner", justify="center")

    for agent_id, score in sorted(verdict.scores.items(), key=lambda x: x[1], reverse=True):
        agent = agents.get(agent_id)
        name = agent.name if agent else agent_id[:8]
        provider = agent.provider if agent else "?"
        is_winner = agent_id == verdict.winner
        winner_mark = "[bold green]WINNER[/bold green]" if is_winner else ""
        table.add_row(name, provider, f"{score:.1f}", winner_mark)

    console.print(table)

    # Reasoning
    console.print()
    console.print(Panel(verdict.reasoning, title="Judge Reasoning", style="dim"))

    # Winning output preview
    winner_output = outputs.get(verdict.winner, "")
    if winner_output:
        preview = winner_output[:500]
        if len(winner_output) > 500:
            preview += "\n... (truncated)"
        winner_agent = agents.get(verdict.winner)
        winner_name = winner_agent.name if winner_agent else "Unknown"
        console.print()
        console.print(
            Panel(preview, title=f"Winning Output ({winner_name})", style="green")
        )


def print_leaderboard(leaderboard: list[dict]) -> None:
    """Print the Elo leaderboard."""
    table = Table(title="Agent Leaderboard")
    table.add_column("#", style="dim", width=4)
    table.add_column("Agent", style="cyan", min_width=20)
    table.add_column("Provider", style="blue")
    table.add_column("Model", style="magenta")
    table.add_column("Elo", style="yellow", justify="right")
    table.add_column("Win%", justify="right")
    table.add_column("Matches", justify="right")
    table.add_column("Champion", justify="center")
    table.add_column("Specializations", style="dim")

    for entry in leaderboard:
        champ = "[bold green]Y[/bold green]" if entry["champion"] else ""
        table.add_row(
            str(entry["rank"]),
            entry["name"],
            entry["provider"],
            entry["model"].split("/")[-1][:20],
            f"{entry['elo']:.0f}",
            f"{entry['win_rate']:.0%}",
            str(entry["matches"]),
            champ,
            ", ".join(entry["specializations"]),
        )

    console.print(table)
