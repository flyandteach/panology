"""
Dedupe state: tracks which articles have already been processed across
weekly runs, so re-runs (or overlapping search topics) don't reprocess or
re-deliver the same article.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

import config


def _key_for(title: str, url: str) -> str:
    """Stable dedupe key from a normalized title + URL."""
    basis = (title or "").strip().lower() + "|" + (url or "").strip().lower()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def load_seen() -> dict:
    if not os.path.exists(config.SEEN_ARTICLES_FILE):
        return {}
    try:
        with open(config.SEEN_ARTICLES_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def save_seen(seen: dict) -> None:
    os.makedirs(config.STATE_DIR, exist_ok=True)
    with open(config.SEEN_ARTICLES_FILE, "w", encoding="utf-8") as fh:
        json.dump(seen, fh, indent=2, sort_keys=True)


def is_seen(seen: dict, title: str, url: str) -> bool:
    return _key_for(title, url) in seen


def mark_seen(seen: dict, title: str, url: str, extra: dict = None) -> None:
    entry = {"title": title, "url": url, "seen_at": datetime.now(timezone.utc).isoformat()}
    if extra:
        entry.update(extra)
    seen[_key_for(title, url)] = entry
