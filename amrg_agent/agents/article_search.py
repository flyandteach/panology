"""
Research-article search agent, backed by the OpenAlex Works API
(https://docs.openalex.org/api-entities/works). Replaces an earlier
Google-Scholar-scraping backend: OpenAlex is a free, documented REST API
with no anti-bot/CAPTCHA wall, and it reports open-access full-text
availability as a first-class field instead of something to infer from a
scraped "[PDF]" link.

Auth/config (all optional -- see config.py):
  OPENALEX_MAILTO    - identify requests for OpenAlex's "polite pool"
                        (better reliability under load). Not an account;
                        just a courtesy query param. Leave unset to use
                        the default shared pool.
  OPENALEX_API_KEY   - a free personal key (https://docs.openalex.org/how-to-use-the-api/api-overview#api-key)
                        for a dedicated rate budget instead of sharing the
                        anonymous tier with every other caller on this
                        network. Not required.

Without either, requests still work -- they just share the lowest-priority
anonymous quota, which can occasionally return 429s under load. That's
handled the same way a hard block would be: the topic is marked
unavailable for this run rather than failing the whole pipeline.
"""

from datetime import datetime, timedelta, timezone

import requests

import config

OPENALEX_WORKS_URL = "https://api.openalex.org/works"


class SearchUnavailableError(Exception):
    """Raised when the search API appears to be rate-limiting or otherwise
    refusing this run (as opposed to a real bug in how we're calling it)."""


def _reconstruct_abstract(inverted_index: dict) -> str:
    """OpenAlex stores abstracts as {word: [position, ...]} to respect
    publisher copyright on the running text. Rebuild the plain text."""
    if not inverted_index:
        return ""
    positions = []
    for word, idxs in inverted_index.items():
        for idx in idxs:
            positions.append((idx, word))
    positions.sort(key=lambda p: p[0])
    return " ".join(word for _, word in positions)


def _format_authors(authorships: list) -> list:
    """['Jane Doe (MIT, NASA Ames)', 'John Smith'] -- name plus any listed
    institutional affiliations, when OpenAlex has them."""
    formatted = []
    for a in authorships or []:
        author = a.get("author") or {}
        name = author.get("display_name") or a.get("raw_author_name") or ""
        if not name:
            continue
        institutions = [i.get("display_name") for i in a.get("institutions") or [] if i.get("display_name")]
        formatted.append(f"{name} ({', '.join(institutions)})" if institutions else name)
    return formatted


def _best_pdf_url(work: dict) -> str:
    """Priority order for a direct full-text link, falling back to
    whatever open_access points at if nothing more specific is available."""
    best_oa = work.get("best_oa_location") or {}
    if best_oa.get("pdf_url"):
        return best_oa["pdf_url"]

    primary = work.get("primary_location") or {}
    if primary.get("is_oa") and primary.get("pdf_url"):
        return primary["pdf_url"]

    return (work.get("open_access") or {}).get("oa_url") or ""


def _source_url(work: dict) -> str:
    primary = work.get("primary_location") or {}
    if primary.get("landing_page_url"):
        return primary["landing_page_url"]
    if work.get("doi"):
        return work["doi"]
    return work.get("id", "")


def _normalize_result(work: dict, topic_key: str) -> dict:
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    return {
        "topic": topic_key,
        "title": (work.get("title") or work.get("display_name") or "").strip(),
        "authors": _format_authors(work.get("authorships")),
        "venue": source.get("display_name", ""),
        "pub_year": work.get("publication_year", ""),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "source_url": _source_url(work),
        "pdf_url": _best_pdf_url(work),
        "num_citations": work.get("cited_by_count", 0),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def search_topic(topic_key: str, query: str, max_results: int = None) -> list:
    """Search OpenAlex for one topic query, newest first, limited to the
    last config.LOOKBACK_DAYS days.

    Returns a list of normalized result dicts:
        {topic, title, authors, venue, pub_year, abstract,
         source_url, pdf_url, num_citations, fetched_at}

    Raises SearchUnavailableError if OpenAlex refuses the request (rate
    limit, etc.) -- callers should treat that as "try again later" for
    this topic, not abort the whole run.
    """
    max_results = max_results or config.MAX_RESULTS_PER_TOPIC
    since = (datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    params = {
        "search": query,
        "sort": "publication_date:desc",
        "per-page": max_results,
        "filter": f"from_publication_date:{since}",
    }
    if config.OPENALEX_MAILTO:
        params["mailto"] = config.OPENALEX_MAILTO
    if config.OPENALEX_API_KEY:
        params["api_key"] = config.OPENALEX_API_KEY

    try:
        resp = requests.get(
            OPENALEX_WORKS_URL, params=params,
            headers={"User-Agent": config.USER_AGENT}, timeout=config.REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        raise SearchUnavailableError(f"OpenAlex request failed: {e}") from e

    if resp.status_code == 429:
        raise SearchUnavailableError(f"OpenAlex rate-limited this request: {resp.text[:300]}")
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAlex returned {resp.status_code}: {resp.text[:300]}")

    works = resp.json().get("results", [])
    return [_normalize_result(w, topic_key) for w in works]


def search_all_topics(topics: dict = None, max_results: int = None) -> dict:
    """Search every configured topic. Returns {topic: {results: [...], blocked: bool, error: str|None}}.

    `blocked` means "this topic's search didn't go through this run"
    (rate-limited or otherwise unavailable) -- kept as the key name for
    compatibility with the rest of the pipeline/email digest, which treats
    it as "try again next week," not a bug to chase.
    """
    topics = topics or config.SEARCH_TOPICS
    report = {}
    for topic_key, query in topics.items():
        try:
            hits = search_topic(topic_key, query, max_results=max_results)
            report[topic_key] = {"results": hits, "blocked": False, "error": None}
        except SearchUnavailableError as e:
            report[topic_key] = {"results": [], "blocked": True, "error": str(e)}
        except Exception as e:
            report[topic_key] = {"results": [], "blocked": False, "error": str(e)}
    return report


def has_public_fulltext(result: dict) -> bool:
    """True if OpenAlex reports a free full-text PDF for this work."""
    return bool(result.get("pdf_url"))
