"""
Export utilities: concatenate approved sections into a manuscript Markdown file.
"""

import os
from datetime import datetime


def export_manuscript(project_memory, export_dir: str) -> str:
    """
    Concatenate all approved sections in outline order and write to export_dir.
    Returns the path to the exported file.
    """
    proj = project_memory.project
    title = proj.get("title", "Untitled").replace(" ", "_")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{title}_{timestamp}.md"
    filepath = os.path.join(export_dir, filename)

    outline = project_memory.get_outline()
    approved_map = {
        s["id"]: s for s in project_memory.get_approved_sections()
    }

    # Build ordered list of approved section IDs from outline
    ordered_sections = []
    for item in outline:
        sid = item.get("id")
        if sid in approved_map:
            ordered_sections.append((item, approved_map[sid]))

    lines = []
    lines.append(f"# {proj.get('title', 'Untitled')}")
    lines.append("")
    lines.append(f"*Genre: {proj.get('genre', '')}*  ")
    lines.append(f"*Audience: {proj.get('audience', '')}*  ")
    lines.append(f"*Exported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Try to read draft files for full content
    drafts_approved_dir = os.path.join(
        os.path.dirname(project_memory.path), "drafts", "approved"
    )

    for outline_item, mem_entry in ordered_sections:
        section_title = outline_item.get("title", mem_entry.get("title", "Section"))
        sid = outline_item.get("id")

        lines.append(f"## {section_title}")
        lines.append("")

        # Try to read the actual draft file
        draft_file = os.path.join(drafts_approved_dir, f"{sid}.md")
        if os.path.exists(draft_file):
            with open(draft_file, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
            lines.append(content)
        else:
            lines.append(f"*[Content for section '{section_title}' not found]*")

        lines.append("")
        lines.append("---")
        lines.append("")

    os.makedirs(export_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return filepath


def save_draft(content: str, section_id: str, drafts_dir: str) -> str:
    """Save a draft to the specified directory. Returns the path."""
    os.makedirs(drafts_dir, exist_ok=True)
    filepath = os.path.join(drafts_dir, f"{section_id}.md")
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)
    return filepath
