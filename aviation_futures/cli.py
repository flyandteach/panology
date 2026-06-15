#!/usr/bin/env python3
"""
Aviation Futures Intelligence — CLI
"""

import os
import sys
import json as _json

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from agent import AviationFuturesAgent, DOMAINS, HORIZON_LABELS

console = Console()


def _print_forecast(result: dict):
    console.print(Panel(
        f"[bold cyan]Aviation Futures Intelligence[/bold cyan]\n"
        f"[dim]Generated: {result.get('generated_at', '—')}[/dim]",
        style="cyan",
    ))

    summary = result.get("executive_summary", "")
    if summary:
        console.print(Panel(summary, title="Executive Summary", style="blue"))

    domains = result.get("domains", {})
    if domains:
        table = Table(title="Domain Signal Overview", show_header=True)
        table.add_column("Domain", style="cyan", max_width=36)
        table.add_column("Signal", justify="right")
        table.add_column("Direction")
        table.add_column("Adoption", justify="right")
        table.add_column("Infra", justify="right")

        direction_colours = {
            "accelerating": "[green]accelerating[/green]",
            "steady": "[yellow]steady[/yellow]",
            "decelerating": "[red]decelerating[/red]",
            "maturing": "[blue]maturing[/blue]",
            "reversing": "[red]reversing[/red]",
        }

        for domain, data in domains.items():
            direction = data.get("trend_direction", "—")
            adoption = data.get("adoption_probability_score")
            infra = data.get("infrastructure_readiness")
            table.add_row(
                domain,
                f"{data.get('signal_strength', 0):.1f}/10",
                direction_colours.get(direction, direction),
                f"{adoption:.0%}" if adoption is not None else "—",
                f"{infra:.0%}" if infra is not None else "—",
            )
        console.print(table)

    themes = result.get("cross_domain_themes", [])
    if themes:
        console.print("\n[bold]Cross-Domain Themes[/bold]")
        for t in themes:
            urgency_colour = {"high": "red", "medium": "yellow", "low": "dim"}.get(t.get("urgency", "low"), "dim")
            console.print(
                f"  [{urgency_colour}]●[/{urgency_colour}] [bold]{t['theme']}[/bold]: {t['description']}"
            )

    flags = result.get("scenario_flags", [])
    if flags:
        console.print("\n[bold]Scenario Flags[/bold]")
        for f in flags:
            prob = f.get("probability", 0)
            console.print(f"  {f['scenario']} ({prob:.0%}): {f['impact']}")

    recs = result.get("top_recommendations", [])
    if recs:
        console.print("\n[bold]Top Recommendations[/bold]")
        for i, r in enumerate(recs, 1):
            console.print(f"  {i}. {r}")


@click.group()
def cli():
    """Aviation Futures Intelligence — trend forecasts, scenario analyses, adoption scores."""


@cli.command("forecast")
@click.option("--horizon", default="mid", type=click.Choice(["near", "mid", "far"]), help="Time horizon.")
@click.option("--domains", default=None, help="Comma-separated domain names to include (default: all).")
@click.option("--focus", default="", help="Optional free-text focus notes.")
@click.option("--json-output", is_flag=True, default=False, help="Print raw JSON.")
def forecast(horizon, domains, focus, json_output):
    """Run a full multi-domain aviation futures forecast."""
    active_domains = [d.strip() for d in domains.split(",")] if domains else None
    console.print(f"[bold]Running Aviation Futures forecast[/bold] (horizon: {HORIZON_LABELS.get(horizon, horizon)}) …")

    agent = AviationFuturesAgent()
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
        progress.add_task("Analysing aviation signals …", total=None)
        result = agent.run_forecast(domains=active_domains, horizon=horizon, focus_notes=focus)

    if json_output:
        console.print(_json.dumps(result, indent=2))
    else:
        _print_forecast(result)


@cli.command("domain")
@click.argument("domain")
@click.option("--horizon", default="mid", type=click.Choice(["near", "mid", "far"]))
@click.option("--json-output", is_flag=True, default=False)
def domain_brief(domain, horizon, json_output):
    """Run a focused brief for a single aviation domain (partial name match supported)."""
    matched = next((d for d in DOMAINS if domain.lower() in d.lower()), domain)
    console.print(f"[bold]Domain brief:[/bold] {matched}")

    agent = AviationFuturesAgent()
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
        progress.add_task(f"Analysing {matched} …", total=None)
        result = agent.run_domain_brief(domain=matched, horizon=horizon)

    if json_output:
        console.print(_json.dumps(result, indent=2))
        return

    console.print(Panel(result.get("narrative", ""), title=matched, style="cyan"))
    console.print(f"  Signal strength: {result.get('signal_strength', '—')}/10")
    console.print(f"  Trend: {result.get('trend_direction', '—')}")
    adoption = result.get("adoption_probability_score")
    infra = result.get("infrastructure_readiness")
    if adoption is not None:
        console.print(f"  Adoption probability: {adoption:.0%}")
    if infra is not None:
        console.print(f"  Infrastructure readiness: {infra:.0%}")

    for label, key in [("Infrastructure gaps", "infrastructure_gaps"), ("Watch signals", "watch_signals")]:
        items = result.get(key, [])
        if items:
            console.print(f"\n[bold]{label}[/bold]")
            prefix = "•" if key == "infrastructure_gaps" else "→"
            for item in items:
                console.print(f"  {prefix} {item}")


@cli.command("scenarios")
@click.option("--json-output", is_flag=True, default=False)
def scenarios(json_output):
    """Generate scenario analyses across all aviation domains."""
    console.print("[bold]Generating aviation scenario analyses …[/bold]")

    agent = AviationFuturesAgent()
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
        progress.add_task("Building scenarios …", total=None)
        result = agent.run_scenario_analysis()

    if json_output:
        console.print(_json.dumps(result, indent=2))
        return

    scenario_list = result.get("scenarios", [])
    table = Table(title="Aviation Futures — Scenario Analysis", show_header=True)
    table.add_column("Scenario", style="bold cyan", max_width=24)
    table.add_column("Prob.", justify="right")
    table.add_column("Trigger", max_width=38)
    table.add_column("Impact / Horizon Shift", max_width=50)

    for s in scenario_list:
        prob = s.get("probability", 0)
        impact = s.get("impact") or s.get("horizon_shift", "—")
        table.add_row(s.get("name", "?"), f"{prob:.0%}", s.get("trigger", "—"), impact)
    console.print(table)

    note = result.get("scenario_matrix_note", "")
    if note:
        console.print(f"\n[dim]{note}[/dim]")


if __name__ == "__main__":
    cli()
