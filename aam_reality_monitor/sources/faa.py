"""Placeholder source connector for future live ingestion.

MVP intentionally avoids live scraping. Use manual evidence entry or CSV import instead.
"""
from __future__ import annotations

from ..models import EvidenceRecord


def collect(*args, **kwargs) -> list[EvidenceRecord]:
    """Return no records until a verified live source integration is implemented."""
    return []
