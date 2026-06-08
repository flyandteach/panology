"""
ProjectMemory: JSON-backed project state for the book agent.
Tracks approved sections, style notes, key terms, and revision history.
"""

import json
import os
from datetime import datetime
from typing import Any


class ProjectMemory:
    """Manages persistent project state stored in a JSON file."""

    EMPTY_STRUCTURE = {
        "project": {
            "title": "",
            "genre": "",
            "audience": "",
            "tone": "",
            "style_profile": "",
            "status": "planning",
        },
        "outline": [],
        "memory": {
            "approved_sections": [],
            "key_terms": {},
            "major_claims": [],
            "used_examples": [],
            "used_metaphors": [],
            "phrases_to_avoid": [],
            "style_notes": [],
            "continuity_notes": [],
        },
        "revision_history": [],
    }

    def __init__(self):
        self._data: dict = {}
        self._path: str = ""

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, project_path: str) -> "ProjectMemory":
        """Load memory from project directory or create fresh if missing."""
        from config import MEMORY_FILENAME

        instance = cls()
        memory_file = os.path.join(project_path, MEMORY_FILENAME)
        instance._path = memory_file

        if os.path.exists(memory_file):
            with open(memory_file, "r", encoding="utf-8") as fh:
                instance._data = json.load(fh)
        else:
            import copy
            instance._data = copy.deepcopy(cls.EMPTY_STRUCTURE)

        return instance

    def save(self) -> None:
        """Persist memory to disk."""
        if not self._path:
            raise RuntimeError("Memory path not set — call load() first.")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Project creation
    # ------------------------------------------------------------------

    def create_new(
        self,
        title: str,
        genre: str,
        audience: str,
        tone: str,
        style_profile: str,
    ) -> None:
        """Initialise a fresh project."""
        import copy

        self._data = copy.deepcopy(self.EMPTY_STRUCTURE)
        self._data["project"].update(
            {
                "title": title,
                "genre": genre,
                "audience": audience,
                "tone": tone,
                "style_profile": style_profile,
                "status": "planning",
                "created_at": datetime.utcnow().isoformat(),
            }
        )

    # ------------------------------------------------------------------
    # Outline management
    # ------------------------------------------------------------------

    def set_outline(self, outline: list) -> None:
        """Replace the full outline list."""
        self._data["outline"] = outline

    def get_outline(self) -> list:
        return self._data.get("outline", [])

    def get_next_unstarted_section(self) -> dict | None:
        """Return the first outline section that has no status or status='pending'."""
        for section in self._data.get("outline", []):
            status = section.get("status", "pending")
            if status in ("pending", ""):
                return section
        return None

    def mark_section_status(self, section_id: str, status: str) -> None:
        for section in self._data.get("outline", []):
            if section.get("id") == section_id:
                section["status"] = status
                return

    # ------------------------------------------------------------------
    # Approved sections
    # ------------------------------------------------------------------

    def add_approved_section(
        self,
        section_id: str,
        title: str,
        summary: str,
        content: str,
    ) -> None:
        """Record a newly approved section in memory."""
        entry = {
            "id": section_id,
            "title": title,
            "summary": summary,
            "word_count": len(content.split()),
            "approved_at": datetime.utcnow().isoformat(),
        }
        self._data["memory"]["approved_sections"].append(entry)
        self.mark_section_status(section_id, "approved")

    def get_approved_sections(self) -> list:
        return self._data["memory"]["approved_sections"]

    # ------------------------------------------------------------------
    # Memory updates
    # ------------------------------------------------------------------

    def update_phrases_to_avoid(self, phrases: list) -> None:
        """Add phrases to the avoid list (deduplicating)."""
        existing = set(self._data["memory"]["phrases_to_avoid"])
        for p in phrases:
            existing.add(p)
        self._data["memory"]["phrases_to_avoid"] = sorted(existing)

    def update_used_metaphors(self, metaphors: list) -> None:
        existing = set(self._data["memory"]["used_metaphors"])
        for m in metaphors:
            existing.add(m)
        self._data["memory"]["used_metaphors"] = sorted(existing)

    def update_key_terms(self, terms: dict) -> None:
        self._data["memory"]["key_terms"].update(terms)

    def add_style_note(self, note: str) -> None:
        self._data["memory"]["style_notes"].append(note)

    def add_continuity_note(self, note: str) -> None:
        self._data["memory"]["continuity_notes"].append(note)

    def add_revision_history(self, entry: dict) -> None:
        entry["timestamp"] = datetime.utcnow().isoformat()
        self._data["revision_history"].append(entry)

    # ------------------------------------------------------------------
    # Context generation
    # ------------------------------------------------------------------

    def get_context_for_agent(self) -> str:
        """Return a formatted string summary of project state for LLM prompts."""
        proj = self._data["project"]
        mem = self._data["memory"]

        lines = [
            "## PROJECT CONTEXT",
            f"Title: {proj.get('title', 'Untitled')}",
            f"Genre: {proj.get('genre', 'Unknown')}",
            f"Audience: {proj.get('audience', 'General')}",
            f"Tone: {proj.get('tone', 'Neutral')}",
            f"Style Profile: {proj.get('style_profile', 'None specified')}",
            f"Status: {proj.get('status', 'planning')}",
            "",
            "## APPROVED SECTIONS SO FAR",
        ]

        approved = mem.get("approved_sections", [])
        if approved:
            for s in approved:
                lines.append(f"- [{s['id']}] {s['title']} ({s.get('word_count', '?')} words)")
                if s.get("summary"):
                    lines.append(f"  Summary: {s['summary']}")
        else:
            lines.append("  (none yet)")

        lines += ["", "## KEY TERMS"]
        kt = mem.get("key_terms", {})
        if kt:
            for term, definition in kt.items():
                lines.append(f"  {term}: {definition}")
        else:
            lines.append("  (none defined)")

        lines += ["", "## PHRASES TO AVOID"]
        pta = mem.get("phrases_to_avoid", [])
        if pta:
            for phrase in pta:
                lines.append(f"  - {phrase}")
        else:
            lines.append("  (none flagged)")

        lines += ["", "## USED METAPHORS"]
        um = mem.get("used_metaphors", [])
        if um:
            for m in um:
                lines.append(f"  - {m}")
        else:
            lines.append("  (none yet)")

        lines += ["", "## STYLE NOTES"]
        sn = mem.get("style_notes", [])
        if sn:
            for note in sn[-5:]:  # last 5 notes
                lines.append(f"  - {note}")
        else:
            lines.append("  (none)")

        lines += ["", "## CONTINUITY NOTES"]
        cn = mem.get("continuity_notes", [])
        if cn:
            for note in cn[-5:]:
                lines.append(f"  - {note}")
        else:
            lines.append("  (none)")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Raw data access
    # ------------------------------------------------------------------

    @property
    def project(self) -> dict:
        return self._data["project"]

    @property
    def data(self) -> dict:
        return self._data

    @property
    def path(self) -> str:
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        self._path = value
