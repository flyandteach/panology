"""
Google Scholar search agent.

Uses the unofficial `scholarly` package to scrape Scholar's public results
page. This is best-effort: Scholar has no public API, scraping it violates
Google's Terms of Service, and Scholar aggressively CAPTCHA-blocks cloud/CI
IP ranges. There is no key-based workaround for that here (see README) --
callers should expect some weekly runs to return zero results for some or
all topics, and should treat a blocked run as "try again later," not as a
bug to chase.

What this module guarantees when it *does* get results: for each hit it
surfaces `eprint_url`, which is exactly the free full-text link ("[PDF]"
or similar) Scholar shows to the right of a result -- this is how the
pipeline decides whether a paper is publicly downloadable.
"""

from datetime import datetime

import config


class ScholarBlockedError(Exception):
    """Raised when Scholar appears to have CAPTCHA-blocked this run."""


def _get_scholarly():
    try:
        from scholarly import scholarly
    except ImportError as e:
        raise RuntimeError(
            "The 'scholarly' package is required for Google Scholar search. "
            "Install it with `pip install scholarly`."
        ) from e
    return scholarly


def search_topic(topic_key: str, query: str, max_results: int = None) -> list:
    """Search Google Scholar for one topic query.

    Returns a list of normalized result dicts:
        {topic, title, authors, venue, pub_year, abstract,
         scholar_url, eprint_url, num_citations}

    Raises ScholarBlockedError if Scholar appears to be CAPTCHA-blocking
    this run (callers should log it and move on to the next topic/week
    rather than retrying in a hot loop).
    """
    max_results = max_results or config.MAX_RESULTS_PER_TOPIC
    scholarly = _get_scholarly()

    results = []
    try:
        search_gen = scholarly.search_pubs(query, sort_by="date")
    except Exception as e:
        _raise_if_blocked(e)
        raise

    try:
        for i, pub in enumerate(search_gen):
            if i >= max_results:
                break
            bib = pub.get("bib", {}) or {}
            results.append({
                "topic": topic_key,
                "title": bib.get("title", "").strip(),
                "authors": bib.get("author", []),
                "venue": bib.get("venue", "") or bib.get("citation", ""),
                "pub_year": bib.get("pub_year", ""),
                "abstract": bib.get("abstract", ""),
                "scholar_url": pub.get("pub_url") or pub.get("url_scholarbtn", ""),
                "eprint_url": pub.get("eprint_url", ""),
                "num_citations": pub.get("num_citations", 0),
                "fetched_at": datetime.utcnow().isoformat(),
            })
    except Exception as e:
        _raise_if_blocked(e)
        # Non-CAPTCHA error partway through iteration: keep what we got.

    return results


def _raise_if_blocked(exc: Exception) -> None:
    text = str(exc).lower()
    markers = ("captcha", "unusual traffic", "blocked", "429", "sorry/index")
    if any(m in text for m in markers):
        raise ScholarBlockedError(
            f"Google Scholar appears to have blocked this run: {exc}"
        ) from exc


def search_all_topics(topics: dict = None, max_results: int = None) -> dict:
    """Search every configured topic. Returns {topic: {results: [...], blocked: bool, error: str|None}}."""
    topics = topics or config.SEARCH_TOPICS
    report = {}
    for topic_key, query in topics.items():
        try:
            hits = search_topic(topic_key, query, max_results=max_results)
            report[topic_key] = {"results": hits, "blocked": False, "error": None}
        except ScholarBlockedError as e:
            report[topic_key] = {"results": [], "blocked": True, "error": str(e)}
        except Exception as e:
            report[topic_key] = {"results": [], "blocked": False, "error": str(e)}
    return report


def has_public_fulltext(result: dict) -> bool:
    """True if Scholar surfaced a free full-text link for this result --
    i.e. the '[PDF]'-style link to the right of the entry."""
    return bool(result.get("eprint_url"))
