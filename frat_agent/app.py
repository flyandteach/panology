#!/usr/bin/env python3
"""
FRAT-as-a-Service CLI
Usage: python -m frat_agent.app assess  [options]
       python -m frat_agent.app log
       python -m frat_agent.app report <report_id>
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from frat_agent.models import MissionRequest
from frat_agent.orchestrator import assess
from frat_agent.utils.audit_log import read_recent
from frat_agent.utils.export import export_text
from frat_agent.config import PAVE_RISK_LABELS


console = Console()

_VERDICT_STYLE = {
    "GO":                       "bold green",
    "PROCEED_WITH_MITIGATIONS": "bold yellow",
    "NO_GO":                    "bold red",
}


# ── assess ────────────────────────────────────────────────────────────────────

@click.group()
def cli() -> None:
    """FRAT-as-a-Service — UAS Flight Risk Assessment Tool"""


@cli.command()
@click.option("--lat",           required=True,  type=float,  help="Launch point latitude (decimal degrees)")
@click.option("--lon",           required=True,  type=float,  help="Launch point longitude (decimal degrees)")
@click.option("--location",      required=True,               help="Human-readable location name")
@click.option("--airport",       required=True,               help="Nearest airport ICAO (e.g. KSEA) for weather")
@click.option("--start",         required=True,               help="Planned start (ISO 8601, e.g. 2026-06-22T14:00:00)")
@click.option("--end",           required=True,               help="Planned end   (ISO 8601)")
@click.option("--altitude",      required=True,  type=int,    help="Max altitude AGL (feet)")
@click.option("--operation",     default="VLOS", show_default=True,
              type=click.Choice(["VLOS","EVLOS","BVLOS"]))
@click.option("--density",       default="populated", show_default=True,
              type=click.Choice(["sparse","populated","gathering"]),
              help="Population density at operation site")
@click.option("--aircraft",      default="DJI Mavic 3", show_default=True)
@click.option("--weight",        default=2.0,    type=float,  show_default=True, help="Aircraft weight (lbs)")
@click.option("--dimension",     default=0.3,    type=float,  show_default=True, help="Characteristic dimension (m)")
@click.option("--pilot",         default="Pilot", show_default=True)
@click.option("--cert",          default="Part 107", show_default=True,
              type=click.Choice(["Part 107","Part 61","student"]))
@click.option("--currency-days", default=15,     type=int,    show_default=True, help="Days since last flight")
@click.option("--hours",         default=50.0,   type=float,  show_default=True, help="Pilot total UAS hours")
@click.option("--night",         is_flag=True,   default=False)
@click.option("--night-current", is_flag=True,   default=False)
@click.option("--over-people",   is_flag=True,   default=False)
@click.option("--schedule-pressure", default=1,  type=click.IntRange(1, 5), show_default=True)
@click.option("--client-pressure",   default=1,  type=click.IntRange(1, 5), show_default=True)
@click.option("--notes",         default="")
@click.option("--no-save",       is_flag=True,   default=False, help="Do not write audit log or export files")
@click.option("--json-out",      is_flag=True,   default=False, help="Print full report JSON to stdout")
def assess_mission(**kwargs: object) -> None:
    """Run a full FRAT assessment for a planned UAS mission."""
    no_save  = kwargs.pop("no_save")
    json_out = kwargs.pop("json_out")

    # Remap click option names to dataclass field names
    mission = MissionRequest(
        lat                  = kwargs["lat"],
        lon                  = kwargs["lon"],
        location_name        = kwargs["location"],
        nearest_airport_icao = kwargs["airport"],
        planned_start        = datetime.fromisoformat(kwargs["start"]),
        planned_end          = datetime.fromisoformat(kwargs["end"]),
        max_altitude_ft_agl  = kwargs["altitude"],
        operation_type       = kwargs["operation"],
        population_density   = kwargs["density"],
        aircraft_make_model  = kwargs["aircraft"],
        aircraft_weight_lbs  = kwargs["weight"],
        aircraft_dimension_m = kwargs["dimension"],
        pilot_name           = kwargs["pilot"],
        pilot_certificate    = kwargs["cert"],
        pilot_currency_days  = kwargs["currency_days"],
        pilot_total_hours    = kwargs["hours"],
        pilot_night_current  = kwargs["night_current"],
        is_night             = kwargs["night"],
        over_people          = kwargs["over_people"],
        schedule_pressure    = kwargs["schedule_pressure"],
        client_pressure      = kwargs["client_pressure"],
        notes                = kwargs["notes"],
    )

    console.print("\n[bold]Fetching live data and computing risk scores…[/bold]")
    report = assess(mission, save=not no_save)

    if json_out:
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    _print_report(report)


def _print_report(report) -> None:
    verdict_style = _VERDICT_STYLE.get(report.verdict, "white")
    console.print()
    console.print(Panel(
        f"[{verdict_style}]{report.verdict_label}[/{verdict_style}]",
        title=f"Report {report.report_id}",
        border_style=verdict_style,
    ))

    if report.hard_stops:
        console.print("\n[bold red]⛔ HARD STOPS[/bold red]")
        for hs in report.hard_stops:
            console.print(f"  [red]• {hs}[/red]")

    # ── Weather ──────────────────────────────────────────────────────────────
    w = report.weather
    if w:
        cat_color = {"VFR": "green", "MVFR": "yellow", "IFR": "red", "LIFR": "red"}.get(w.flight_category, "white")
        console.print(f"\n[bold]Weather[/bold]  [{cat_color}]{w.flight_category}[/{cat_color}]  "
                      f"Wind {w.wind_dir_deg or '?'}°/{w.wind_speed_kt}kt"
                      + (f" G{w.wind_gust_kt}kt" if w.wind_gust_kt else "")
                      + f"  Vis {w.visibility_sm} SM  Ceil {w.ceiling_ft or 'CLR'} ft")

    # ── PAVE table ────────────────────────────────────────────────────────────
    pave_table = Table(title="PAVE Scores", box=box.SIMPLE)
    pave_table.add_column("Dimension",  style="bold")
    pave_table.add_column("Score", justify="center")
    pave_table.add_column("Label")
    pave_table.add_column("Key Factors")

    p = report.pave
    _PAVE_COLOR = {1: "green", 2: "green", 3: "yellow", 4: "red", 5: "bold red"}
    for dim, score, factors in [
        ("Pilot",       p.pilot,       p.pilot_factors),
        ("Aircraft",    p.aircraft,    p.aircraft_factors),
        ("Environment", p.environment, p.environment_factors),
        ("External",    p.external,    p.external_factors),
    ]:
        c = _PAVE_COLOR.get(score, "white")
        pave_table.add_row(
            dim,
            f"[{c}]{score}/5[/{c}]",
            PAVE_RISK_LABELS.get(score, "?"),
            (factors[0][:80] + "…") if factors else "—",
        )
    pave_table.add_row("[bold]Average[/bold]", f"[bold]{p.average:.1f}[/bold]", "", "")
    console.print(pave_table)

    # ── SORA ─────────────────────────────────────────────────────────────────
    s = report.sora
    sail_roman = ["", "I", "II", "III", "IV", "V", "VI"]
    console.print(
        f"[bold]SORA 2.5[/bold]  iGRC {s.igrc}  ARC-{s.arc_label.upper()}  "
        f"SAIL {sail_roman[s.sail] if 1 <= s.sail <= 6 else s.sail}"
    )

    # ── Mitigations ───────────────────────────────────────────────────────────
    if report.mitigations:
        console.print("\n[bold]Required Mitigations[/bold]")
        for m in report.mitigations:
            tag = "[red]⛔ HARD STOP[/red] " if m.is_hard_stop else ""
            console.print(f"  {tag}[cyan]{m.dimension.upper()}[/cyan] — {m.risk_factor}")
            console.print(f"    → {m.action}")

    # ── Data warnings ─────────────────────────────────────────────────────────
    if report.data_warnings:
        console.print("\n[yellow]Data warnings:[/yellow]")
        for dw in report.data_warnings:
            console.print(f"  [yellow]⚠[/yellow] {dw}")

    console.print(f"\nReport saved → reports/{report.report_id}.txt  |  .json")
    console.print()


# ── log ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--n", default=10, show_default=True, help="Number of recent entries to show")
def log(n: int) -> None:
    """Show recent assessment records from the audit log."""
    records = read_recent(n)
    if not records:
        console.print("[yellow]No assessment records found.[/yellow]")
        return

    table = Table(title="Recent Assessments", box=box.SIMPLE)
    table.add_column("Report ID")
    table.add_column("Generated")
    table.add_column("Location")
    table.add_column("Pilot")
    table.add_column("Verdict", style="bold")

    for r in reversed(records):
        v = r.get("verdict", "")
        v_style = {"GO": "green", "PROCEED_WITH_MITIGATIONS": "yellow", "NO_GO": "red"}.get(v, "white")
        table.add_row(
            r.get("report_id", "?")[:24],
            r.get("generated_at", "?")[:19],
            r.get("mission", {}).get("location_name", "?")[:30],
            r.get("mission", {}).get("pilot_name", "?"),
            f"[{v_style}]{v}[/{v_style}]",
        )
    console.print(table)


# ── report ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("report_id")
def report(report_id: str) -> None:
    """Print the text report for a given Report ID."""
    from pathlib import Path
    txt_path = Path(__file__).parent / "reports" / f"{report_id}.txt"
    if not txt_path.exists():
        console.print(f"[red]Report not found: {txt_path}[/red]")
        sys.exit(1)
    console.print(txt_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    cli()
