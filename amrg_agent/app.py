#!/usr/bin/env python3
"""
AMRG Weekly Literature Watch Agent -- Main CLI Entry Point
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

import click
from rich.console import Console
from rich.table import Table

import config
import pipeline

console = Console()


@click.group()
def cli():
    """AMRG weekly literature-watch agent (AAM / UAM / eVTOL / electric aircraft / vertiports / AI in aviation)."""


@cli.command("run-weekly")
@click.option("--dry-run", is_flag=True, help="Search, download, and score, but skip the Drive upload and dedupe write.")
@click.option("--max-results", default=None, type=int, help="Override max results per topic (default: config.MAX_RESULTS_PER_TOPIC).")
@click.option("--report-json", default=None, type=click.Path(), help="Write the full run report as JSON to this path.")
def run_weekly(dry_run, max_results, report_json):
    """Run the full weekly search -> filter -> summarize -> upload pipeline once."""
    console.print("[bold]AMRG weekly run starting...[/bold]")
    report = pipeline.run_weekly(max_results_per_topic=max_results, dry_run=dry_run)

    table = Table(title="Search results by topic")
    table.add_column("Topic")
    table.add_column("Hits")
    table.add_column("Blocked?")
    for topic, info in report["search_report"].items():
        table.add_row(topic, str(info["count"]), "[red]yes[/red]" if info["blocked"] else "no")
    console.print(table)

    if report["processed"]:
        ptable = Table(title="Processed articles")
        ptable.add_column("Title")
        ptable.add_column("Score")
        ptable.add_column("Figures")
        ptable.add_column("Drive URL")
        for a in report["processed"]:
            ptable.add_row(
                (a["title"] or "")[:60],
                str(a["final_writing_score"]),
                str(a["figure_count"]),
                a.get("drive_url") or (a.get("docx_path") or "-"),
            )
        console.print(ptable)
    else:
        console.print("[yellow]No new articles with public full text were found this run.[/yellow]")

    if report["skipped"]:
        console.print(f"[dim]Skipped {len(report['skipped'])} results (no public full text or already seen).[/dim]")

    if report["errors"]:
        console.print(f"[red]{len(report['errors'])} error(s) during this run:[/red]")
        for e in report["errors"]:
            console.print(f"  - [{e.get('stage', '?')}] {e.get('title') or e.get('topic')}: {e['error']}")

    if report_json:
        # Drop full markdown bodies from the JSON dump to keep it readable;
        # they're already written out as .docx files.
        slim = dict(report)
        slim["processed"] = [
            {k: v for k, v in a.items() if k != "document_markdown"} for a in report["processed"]
        ]
        with open(report_json, "w", encoding="utf-8") as fh:
            json.dump(slim, fh, indent=2)
        console.print(f"[dim]Run report written to {report_json}[/dim]")


@cli.command("show-config")
def show_config():
    """Print the active topic queries and key settings."""
    console.print("[bold]Search topics:[/bold]")
    for key, query in config.SEARCH_TOPICS.items():
        console.print(f"  {key}: {query}")
    console.print(f"\nMax results/topic: {config.MAX_RESULTS_PER_TOPIC}")
    console.print(f"Drive folder configured: {'yes' if config.GOOGLE_DRIVE_FOLDER_ID else 'no'}")
    console.print(f"Anthropic key configured: {'yes' if os.environ.get('ANTHROPIC_API_KEY') else 'no'}")


if __name__ == "__main__":
    cli()
