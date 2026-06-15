#!/usr/bin/env python3
"""
Recursive Editorial Book Agent — Main CLI Entry Point
"""

import os
import sys
import json
import shutil

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

import config
from utils.memory import ProjectMemory
from utils.metrics import TextMetrics
from utils.export import export_manuscript, save_draft
from agents.architect import ArchitectAgent
from agents.drafter import DrafterAgent
from agents.line_editor import LineEditorAgent
from agents.repetition_checker import RepetitionCheckerAgent
from agents.audience_critic import AudienceCriticAgent
from agents.quality_gate import QualityGateAgent

console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_project(project_dir: str) -> ProjectMemory:
    """Load or fail if memory is missing."""
    memory = ProjectMemory.load(project_dir)
    if not memory.project.get("title"):
        console.print(
            f"[red]No project found at {project_dir}. Run `new-project` first.[/red]"
        )
        sys.exit(1)
    return memory


def _save_current_draft(content: str, section_id: str, project_dir: str) -> str:
    current_dir = os.path.join(project_dir, config.DRAFTS_CURRENT_DIR)
    return save_draft(content, section_id, current_dir)


def _save_approved_draft(content: str, section_id: str, project_dir: str) -> str:
    approved_dir = os.path.join(project_dir, config.DRAFTS_APPROVED_DIR)
    return save_draft(content, section_id, approved_dir)


def _save_rejected_draft(content: str, section_id: str, project_dir: str) -> str:
    rejected_dir = os.path.join(project_dir, config.DRAFTS_REJECTED_DIR)
    return save_draft(content, section_id, rejected_dir)


def _consolidate_issues(*review_results) -> list:
    """Merge issue lists from multiple review dicts."""
    all_issues = []
    for result in review_results:
        if isinstance(result, dict):
            all_issues.extend(result.get("issues", []))
    return all_issues


def _extract_scores(line_edit_result: dict, rep_result: dict, audience_result: dict) -> dict:
    """Extract scores dict for quality gate."""
    # Continuity score comes from repetition checker (it also tracks cross-section consistency)
    return {
        "line_edit": line_edit_result.get("score", 0.0),
        "repetition": rep_result.get("score", 0.0),
        "continuity": rep_result.get("score", 0.0),  # Use rep score as proxy for continuity
        "critical_audience": audience_result.get("score", 0.0),
    }


def _print_revision_summary(cycle: int, scores: dict, gate_result: dict):
    """Print a brief summary after each revision cycle."""
    table = Table(title=f"Revision Cycle {cycle} Results", show_header=True)
    table.add_column("Dimension", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Status", justify="center")

    for dim, data in gate_result["scorecard"].items():
        status = "[green]✓ PASS[/green]" if data["passed"] else "[red]✗ FAIL[/red]"
        table.add_row(
            data["label"],
            f"{data['score']:.1f}",
            f"{data['threshold']:.1f}",
            status,
        )

    console.print(table)


def _run_full_pipeline(
    memory: ProjectMemory,
    section: dict,
    project_dir: str,
) -> tuple:
    """
    Run the complete draft-review-gate pipeline.
    Returns (best_draft, best_score, best_gate_result, all_cycle_results).
    """
    drafter = DrafterAgent()
    line_editor = LineEditorAgent()
    rep_checker = RepetitionCheckerAgent()
    audience_critic = AudienceCriticAgent()
    quality_gate = QualityGateAgent()
    metrics_engine = TextMetrics()

    section_id = section["id"]
    section_brief = section.get("brief", "Write this section.")
    best_draft = ""
    best_overall = 0.0
    best_gate_result = None
    all_cycle_results = []

    # Issues to target in next revision
    pending_issues = []

    for cycle in range(1, config.MAX_REVISION_CYCLES + 1):
        console.print(f"\n[bold blue]── Cycle {cycle}/{config.MAX_REVISION_CYCLES} ──[/bold blue]")

        with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
            # Step 1: Draft
            task = progress.add_task("Drafting section...", total=None)
            if cycle == 1:
                draft = drafter.draft_section(memory, section, {})
            else:
                # On revision cycles, inject issues into the brief
                augmented_section = dict(section)
                if pending_issues:
                    issues_text = "\n".join(f"- {i}" for i in pending_issues[:5])
                    augmented_section["brief"] = (
                        section_brief + "\n\nPRIOR ISSUES TO ADDRESS:\n" + issues_text
                    )
                draft = drafter.draft_section(memory, augmented_section, {})

            _save_current_draft(draft, section_id, project_dir)

            # Step 2: Metrics
            progress.update(task, description="Computing text metrics...")
            metrics = metrics_engine.analyze(draft)

            # Step 3: Line edit
            progress.update(task, description="Running line editor review...")
            line_edit_result = line_editor.review(draft, memory, metrics)
            if line_edit_result.get("revised_draft"):
                draft = line_edit_result["revised_draft"]

            # Step 4: Repetition check
            progress.update(task, description="Checking for repetition...")
            rep_result = rep_checker.review(draft, memory, metrics)
            if rep_result.get("revised_draft"):
                draft = rep_result["revised_draft"]

            # Step 5: Audience critique
            progress.update(task, description="Running audience critique...")
            audience_result = audience_critic.review(draft, memory, section_brief)

            # Step 6: Quality gate
            progress.update(task, description="Evaluating quality gate...")
            scores = _extract_scores(line_edit_result, rep_result, audience_result)
            all_issues = _consolidate_issues(line_edit_result, rep_result, audience_result)
            gate_result = quality_gate.evaluate(scores, all_issues)

        # Track best draft
        overall = gate_result["overall_score"]
        if overall > best_overall:
            best_overall = overall
            best_draft = draft
            best_gate_result = gate_result

        cycle_record = {
            "cycle": cycle,
            "scores": scores,
            "gate_result": gate_result,
            "issues": all_issues,
        }
        all_cycle_results.append(cycle_record)

        _print_revision_summary(cycle, scores, gate_result)

        if gate_result["pass"]:
            console.print(f"[bold green]Quality gate PASSED in cycle {cycle}![/bold green]")
            return best_draft, best_overall, best_gate_result, all_cycle_results

        # Prepare issues for next cycle
        pending_issues = all_issues[:8]
        failed_dims = [f["dimension"] for f in gate_result.get("failed_thresholds", [])]
        if failed_dims:
            console.print(f"[yellow]Failed dimensions: {', '.join(failed_dims)}[/yellow]")
        console.print(f"[yellow]Targeting {len(pending_issues)} issues in next cycle...[/yellow]")

    console.print(
        f"\n[bold yellow]Maximum revision cycles ({config.MAX_REVISION_CYCLES}) reached.[/bold yellow]"
    )
    console.print(f"Best overall score achieved: [bold]{best_overall:.2f}[/bold]")
    return best_draft, best_overall, best_gate_result, all_cycle_results


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@click.group()
@click.option("--project-dir", "-p", default=".", show_default=True,
              help="Path to the project directory.")
@click.pass_context
def cli(ctx, project_dir):
    """Recursive Editorial Book Agent — manuscript production system."""
    ctx.ensure_object(dict)
    ctx.obj["project_dir"] = os.path.abspath(project_dir)


@cli.command("new-project")
@click.pass_context
def new_project(ctx):
    """Create a new book project interactively."""
    project_dir = ctx.obj["project_dir"]
    os.makedirs(project_dir, exist_ok=True)

    console.print(Panel("[bold]New Book Project Setup[/bold]", style="blue"))

    title = click.prompt("  Book title")
    genre = click.prompt("  Genre (e.g. business nonfiction, memoir, self-help)")
    audience = click.prompt("  Target audience (e.g. senior engineers, general nonfiction readers)")
    tone = click.prompt("  Tone (e.g. analytical, conversational, provocative)")
    style_profile = click.prompt(
        "  Style profile (e.g. 'Malcolm Gladwell — accessible but rigorous; story-first')"
    )

    # Create directory structure
    for subdir in [
        "memory", "drafts/current", "drafts/approved", "drafts/rejected", "exports"
    ]:
        os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

    memory = ProjectMemory.load(project_dir)
    memory.create_new(title, genre, audience, tone, style_profile)
    memory.save()

    console.print(f"\n[green]Project created at: {project_dir}[/green]")
    console.print(f"  Title: {title}")
    console.print(f"  Genre: {genre}")
    console.print(f"  Audience: {audience}")
    console.print("\nNext step: Run [bold]create-outline[/bold]")


@cli.command("load-project")
@click.argument("path")
@click.pass_context
def load_project(ctx, path):
    """Load an existing project and show its status."""
    project_dir = os.path.abspath(path)
    memory = _load_project(project_dir)
    ctx.obj["project_dir"] = project_dir

    proj = memory.project
    console.print(Panel(f"[bold]{proj['title']}[/bold]", subtitle=proj.get("genre", ""), style="blue"))
    console.print(f"  Audience: {proj.get('audience')}")
    console.print(f"  Status: {proj.get('status')}")

    outline = memory.get_outline()
    if outline:
        console.print(f"\n  Outline: {len(outline)} sections")
        for s in outline:
            status_icon = "✓" if s.get("status") == "approved" else "○"
            console.print(f"    {status_icon} [{s['id']}] {s['title']}")
    else:
        console.print("  No outline yet. Run [bold]create-outline[/bold].")


@cli.command("create-outline")
@click.option("--input", "-i", "user_input", default="",
              help="Additional instructions for the architect.")
@click.pass_context
def create_outline(ctx, user_input):
    """Generate a book outline using the Architect Agent."""
    project_dir = ctx.obj["project_dir"]
    memory = _load_project(project_dir)

    if not user_input:
        user_input = click.prompt(
            "Additional instructions for the architect (or press Enter to skip)",
            default="",
        )

    console.print("\n[blue]Running Architect Agent...[/blue]")
    agent = ArchitectAgent()

    with Progress(SpinnerColumn(), TextColumn("Generating outline..."), transient=True) as p:
        p.add_task("", total=None)
        outline_data = agent.create_outline(memory, user_input or "Create a compelling book outline.")

    sections = outline_data.get("sections", [])
    if not sections:
        console.print("[red]Architect returned no sections. Check the response.[/red]")
        console.print(json.dumps(outline_data, indent=2))
        return

    memory.set_outline(sections)
    if outline_data.get("notes"):
        memory.add_style_note(outline_data["notes"])
    memory.save()

    console.print(f"\n[green]Outline created with {len(sections)} sections:[/green]")
    for s in sections:
        console.print(f"  [{s['id']}] {s['title']} (~{s.get('target_word_count', '?')} words)")

    console.print("\nNext step: Run [bold]write-next-section[/bold]")


@cli.command("write-next-section")
@click.pass_context
def write_next_section(ctx):
    """Run the full pipeline on the next unstarted section."""
    project_dir = ctx.obj["project_dir"]
    memory = _load_project(project_dir)

    section = memory.get_next_unstarted_section()
    if not section:
        console.print("[green]All sections have been written or approved![/green]")
        return

    console.print(
        Panel(
            f"[bold]Writing: {section['title']}[/bold]\n"
            f"Brief: {section.get('brief', '')}\n"
            f"Target: ~{section.get('target_word_count', '?')} words",
            style="blue",
        )
    )

    memory.mark_section_status(section["id"], "in_progress")
    memory.save()

    best_draft, best_score, best_gate_result, cycle_results = _run_full_pipeline(
        memory, section, project_dir
    )

    # Display final scorecard
    quality_gate = QualityGateAgent()
    scorecard_display = quality_gate.generate_scorecard_display(best_gate_result)
    console.print("\n" + scorecard_display)

    # Show a preview of the draft
    words = best_draft.split()
    preview = " ".join(words[:80]) + ("..." if len(words) > 80 else "")
    console.print(f"\n[bold]Draft Preview:[/bold]\n{preview}\n")

    # Ask for user decision
    console.print("[bold]What would you like to do?[/bold]")
    console.print("  [A] Approve this draft")
    console.print("  [R] Request another revision")
    console.print("  [X] Reject and mark as failed")
    console.print("  [P] Pause (save draft and come back later)")

    while True:
        choice = click.prompt("Choice", type=click.Choice(["A", "R", "X", "P"], case_sensitive=False))
        choice = choice.upper()
        if choice == "A":
            _approve_section(memory, section, best_draft, project_dir)
            break
        elif choice == "R":
            console.print("[yellow]Launching another revision round...[/yellow]")
            best_draft, best_score, best_gate_result, extra_cycles = _run_full_pipeline(
                memory, section, project_dir
            )
            scorecard_display = quality_gate.generate_scorecard_display(best_gate_result)
            console.print("\n" + scorecard_display)
        elif choice == "X":
            _save_rejected_draft(best_draft, section["id"], project_dir)
            memory.mark_section_status(section["id"], "rejected")
            memory.add_revision_history({
                "section_id": section["id"],
                "action": "rejected",
                "final_score": best_score,
            })
            memory.save()
            console.print(f"[red]Section '{section['title']}' rejected.[/red]")
            break
        elif choice == "P":
            _save_current_draft(best_draft, section["id"], project_dir)
            memory.mark_section_status(section["id"], "paused")
            memory.save()
            console.print(f"[yellow]Section paused. Draft saved to drafts/current/{section['id']}.md[/yellow]")
            break


def _approve_section(memory: ProjectMemory, section: dict, draft: str, project_dir: str):
    """Approve a section: save draft, update memory, mark done."""
    section_id = section["id"]

    # Generate summary (first 2 sentences)
    sentences = draft.replace("\n", " ").split(". ")
    summary = ". ".join(sentences[:2]) + ("." if len(sentences) > 2 else "")
    summary = summary[:400]

    _save_approved_draft(draft, section_id, project_dir)
    memory.add_approved_section(
        section_id=section_id,
        title=section["title"],
        summary=summary,
        content=draft,
    )
    memory.add_revision_history({
        "section_id": section_id,
        "action": "approved",
    })
    memory.save()

    console.print(f"[bold green]✓ Section '{section['title']}' approved and saved![/bold green]")
    console.print(f"  Draft: drafts/approved/{section_id}.md")

    remaining = [s for s in memory.get_outline() if s.get("status") not in ("approved", "rejected")]
    if remaining:
        console.print(f"  Next: [bold]{remaining[0]['title']}[/bold]")
    else:
        console.print("  [bold green]All sections complete! Run export-manuscript.[/bold green]")


@cli.command("review-current-section")
@click.pass_context
def review_current_section(ctx):
    """Run the review pipeline on the current draft without drafting."""
    project_dir = ctx.obj["project_dir"]
    memory = _load_project(project_dir)

    section = memory.get_next_unstarted_section()
    if not section:
        console.print("[yellow]No section currently in progress.[/yellow]")
        return

    section_id = section["id"]
    draft_path = os.path.join(project_dir, config.DRAFTS_CURRENT_DIR, f"{section_id}.md")

    if not os.path.exists(draft_path):
        console.print(f"[red]No current draft found at {draft_path}[/red]")
        return

    with open(draft_path, "r", encoding="utf-8") as fh:
        draft = fh.read()

    metrics_engine = TextMetrics()
    metrics = metrics_engine.analyze(draft)

    console.print("[blue]Running review pipeline on existing draft...[/blue]")

    line_editor = LineEditorAgent()
    rep_checker = RepetitionCheckerAgent()
    audience_critic = AudienceCriticAgent()
    quality_gate = QualityGateAgent()

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
        t = progress.add_task("Line editing...", total=None)
        line_edit_result = line_editor.review(draft, memory, metrics)
        progress.update(t, description="Repetition check...")
        rep_result = rep_checker.review(draft, memory, metrics)
        progress.update(t, description="Audience critique...")
        audience_result = audience_critic.review(draft, memory, section.get("brief", ""))

    scores = _extract_scores(line_edit_result, rep_result, audience_result)
    all_issues = _consolidate_issues(line_edit_result, rep_result, audience_result)
    gate_result = quality_gate.evaluate(scores, all_issues)

    scorecard_display = quality_gate.generate_scorecard_display(gate_result)
    console.print("\n" + scorecard_display)

    if all_issues:
        console.print("\n[bold]Issues found:[/bold]")
        for i, issue in enumerate(all_issues[:10], 1):
            console.print(f"  {i}. {issue}")


@cli.command("approve-current-section")
@click.pass_context
def approve_current_section(ctx):
    """Manually approve the current section draft."""
    project_dir = ctx.obj["project_dir"]
    memory = _load_project(project_dir)

    section = memory.get_next_unstarted_section()
    if not section:
        console.print("[yellow]No section to approve.[/yellow]")
        return

    section_id = section["id"]
    draft_path = os.path.join(project_dir, config.DRAFTS_CURRENT_DIR, f"{section_id}.md")

    if not os.path.exists(draft_path):
        console.print(f"[red]No draft found at {draft_path}[/red]")
        return

    with open(draft_path, "r", encoding="utf-8") as fh:
        draft = fh.read()

    if click.confirm(f"Approve section '{section['title']}'?"):
        _approve_section(memory, section, draft, project_dir)
    else:
        console.print("Approval cancelled.")


@cli.command("show-scorecard")
@click.pass_context
def show_scorecard(ctx):
    """Display the current project scorecard and progress."""
    project_dir = ctx.obj["project_dir"]
    memory = _load_project(project_dir)

    proj = memory.project
    outline = memory.get_outline()
    approved = memory.get_approved_sections()

    console.print(Panel(f"[bold]{proj['title']}[/bold]", style="blue"))

    table = Table(title="Section Status")
    table.add_column("ID", style="dim")
    table.add_column("Title")
    table.add_column("Status", justify="center")
    table.add_column("Words", justify="right")

    approved_ids = {s["id"] for s in approved}
    approved_words = {s["id"]: s.get("word_count", 0) for s in approved}

    for s in outline:
        sid = s.get("id", "?")
        status = s.get("status", "pending")
        status_display = {
            "approved": "[green]✓ Approved[/green]",
            "rejected": "[red]✗ Rejected[/red]",
            "in_progress": "[yellow]⟳ In Progress[/yellow]",
            "paused": "[yellow]⏸ Paused[/yellow]",
            "pending": "[dim]○ Pending[/dim]",
        }.get(status, status)

        words = str(approved_words.get(sid, "—")) if sid in approved_ids else "—"
        table.add_row(sid, s.get("title", "?"), status_display, words)

    console.print(table)

    total_words = sum(s.get("word_count", 0) for s in approved)
    console.print(f"\n  Approved sections: {len(approved)}/{len(outline)}")
    console.print(f"  Total approved words: {total_words:,}")


@cli.command("show-memory")
@click.pass_context
def show_memory(ctx):
    """Display the current project memory state."""
    project_dir = ctx.obj["project_dir"]
    memory = _load_project(project_dir)

    console.print(memory.get_context_for_agent())

    hist = memory.data.get("revision_history", [])
    if hist:
        console.print(f"\n## REVISION HISTORY ({len(hist)} entries)")
        for entry in hist[-5:]:
            console.print(
                f"  [{entry.get('timestamp', '?')}] "
                f"{entry.get('section_id', '?')} — {entry.get('action', '?')}"
            )


@cli.command("export-manuscript")
@click.pass_context
def export_manuscript_cmd(ctx):
    """Export all approved sections as a single Markdown manuscript."""
    project_dir = ctx.obj["project_dir"]
    memory = _load_project(project_dir)

    approved = memory.get_approved_sections()
    if not approved:
        console.print("[yellow]No approved sections to export.[/yellow]")
        return

    export_dir = os.path.join(project_dir, config.EXPORTS_DIR)
    filepath = export_manuscript(memory, export_dir)

    console.print(f"[green]Manuscript exported to:[/green] {filepath}")
    console.print(f"  Sections: {len(approved)}")
    total_words = sum(s.get("word_count", 0) for s in approved)
    console.print(f"  Total words: {total_words:,}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli(obj={})
