"""Metrics and reporting for tracking improvement over time."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mobius.config import MobiusConfig
from mobius.db import row_to_dict

console = Console()


@dataclass
class ExperimentReport:
    """Summary of a batch experiment."""

    total_rounds: int
    successful_rounds: int
    voided_rounds: int
    avg_winning_score: float
    avg_competitor_count: float
    unique_winners: int
    winner_distribution: dict[str, int]  # agent_name -> win count
    elo_trajectory: list[dict]  # [{round, agent, elo}, ...]
    score_trajectory: list[float]  # winning score per round
    memory_hits: int  # times memory influenced selection


def generate_report(conn: sqlite3.Connection, config: MobiusConfig, last_n: int | None = None) -> ExperimentReport:
    """Generate a report from match history."""
    query = "SELECT * FROM matches ORDER BY created_at ASC"
    if last_n:
        query = f"SELECT * FROM matches ORDER BY created_at DESC LIMIT {last_n}"

    rows = conn.execute(query).fetchall()
    if last_n:
        rows = list(reversed(rows))

    matches = [row_to_dict(dict(r)) for r in rows]

    total = len(matches)
    voided = sum(1 for m in matches if m.get("voided"))
    successful = total - voided

    # Winner distribution
    winner_dist: dict[str, int] = {}
    scores: list[float] = []
    competitor_counts: list[float] = []

    for m in matches:
        if m.get("voided"):
            continue
        winner_id = m.get("winner_id")
        if winner_id:
            # Look up agent name
            agent_row = conn.execute("SELECT name FROM agents WHERE id = ?", (winner_id,)).fetchone()
            name = agent_row["name"] if agent_row else winner_id[:8]
            winner_dist[name] = winner_dist.get(name, 0) + 1

        match_scores = m.get("scores", {})
        if isinstance(match_scores, str):
            match_scores = json.loads(match_scores)
        if match_scores:
            scores.append(max(match_scores.values()))

        comp_ids = m.get("competitor_ids", [])
        if isinstance(comp_ids, str):
            comp_ids = json.loads(comp_ids)
        competitor_counts.append(len(comp_ids))

    # Elo trajectory (snapshot after each match)
    elo_trajectory: list[dict] = []
    agents_cache = {}
    for i, m in enumerate(matches):
        if m.get("voided"):
            continue
        winner_id = m.get("winner_id")
        if winner_id:
            if winner_id not in agents_cache:
                row = conn.execute("SELECT name, elo_rating FROM agents WHERE id = ?", (winner_id,)).fetchone()
                if row:
                    agents_cache[winner_id] = row["name"]
            elo_trajectory.append({
                "round": i + 1,
                "winner": agents_cache.get(winner_id, winner_id[:8]),
                "score": scores[len(elo_trajectory)] if len(elo_trajectory) < len(scores) else 0,
            })

    return ExperimentReport(
        total_rounds=total,
        successful_rounds=successful,
        voided_rounds=voided,
        avg_winning_score=sum(scores) / len(scores) if scores else 0,
        avg_competitor_count=sum(competitor_counts) / len(competitor_counts) if competitor_counts else 0,
        unique_winners=len(winner_dist),
        winner_distribution=winner_dist,
        elo_trajectory=elo_trajectory,
        score_trajectory=scores,
        memory_hits=0,  # TODO: track this
    )


def print_report(report: ExperimentReport, title: str = "Experiment Report") -> None:
    """Print a rich report to the terminal."""
    console.print()
    console.print(Panel(f"[bold]{title}[/bold]", style="blue"))

    # Summary stats
    console.print(f"  Rounds: {report.successful_rounds}/{report.total_rounds} successful ({report.voided_rounds} voided)")
    console.print(f"  Avg winning score: [yellow]{report.avg_winning_score:.1f}/30[/yellow]")
    console.print(f"  Avg competitors per round: {report.avg_competitor_count:.1f}")
    console.print(f"  Unique winners: {report.unique_winners}")
    console.print()

    # Winner distribution
    table = Table(title="Winner Distribution")
    table.add_column("Agent", style="cyan")
    table.add_column("Wins", justify="right", style="green")
    table.add_column("Bar", min_width=20)

    max_wins = max(report.winner_distribution.values()) if report.winner_distribution else 1
    for name, wins in sorted(report.winner_distribution.items(), key=lambda x: x[1], reverse=True):
        bar_len = int((wins / max_wins) * 20)
        bar = "[green]" + "#" * bar_len + "[/green]" + "." * (20 - bar_len)
        table.add_row(name, str(wins), bar)

    console.print(table)

    # Score trend (ASCII sparkline)
    if len(report.score_trajectory) >= 2:
        console.print()
        console.print("[bold]Score Trend:[/bold]")
        scores = report.score_trajectory
        min_s, max_s = min(scores), max(scores)
        range_s = max_s - min_s if max_s > min_s else 1
        spark_chars = " _.-=^*#"
        sparkline = ""
        for s in scores:
            idx = int((s - min_s) / range_s * (len(spark_chars) - 1))
            sparkline += spark_chars[idx]
        console.print(f"  [{min_s:.0f}] {sparkline} [{max_s:.0f}]")

        # Trend direction
        first_half = sum(scores[:len(scores)//2]) / (len(scores)//2) if len(scores) >= 2 else 0
        second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2) if len(scores) >= 2 else 0
        if second_half > first_half:
            console.print(f"  [green]Trending UP[/green] ({first_half:.1f} -> {second_half:.1f})")
        elif second_half < first_half:
            console.print(f"  [red]Trending DOWN[/red] ({first_half:.1f} -> {second_half:.1f})")
        else:
            console.print(f"  [yellow]Flat[/yellow] ({first_half:.1f})")

    # Round-by-round
    if report.elo_trajectory:
        console.print()
        round_table = Table(title="Round History")
        round_table.add_column("#", style="dim", width=4)
        round_table.add_column("Winner", style="cyan")
        round_table.add_column("Score", justify="right", style="yellow")

        for entry in report.elo_trajectory:
            round_table.add_row(
                str(entry["round"]),
                entry["winner"],
                f"{entry['score']:.0f}",
            )
        console.print(round_table)
