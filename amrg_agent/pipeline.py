"""
End-to-end weekly pipeline:

  1. Search Google Scholar for each configured topic (agents/scholar_search.py)
  2. Keep only results with a public full-text link, not already processed
  3. Download the PDF and extract text + figures (agents/pdf_extract.py)
  4. Run the heuristic fact-check (agents/fact_check.py)
  5. Score writing quality (agents/scoring.py)
  6. Generate the AMRG summary document (agents/summarizer.py)
  7. Render to .docx and upload to Google Drive (agents/drive_upload.py)
  8. Record the article as seen (utils/state.py)

Any failure on an individual article (bad download, blocked Scholar page,
etc.) is caught and logged in the run report; it never aborts the rest of
the run.
"""

import os
import traceback

import config
from agents import scholar_search, pdf_extract, fact_check, scoring, summarizer, drive_upload
from utils import state


def run_weekly(topics: dict = None, max_results_per_topic: int = None, dry_run: bool = False) -> dict:
    """Run the full pipeline once. Returns a run report dict."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.DOWNLOADS_DIR, exist_ok=True)

    seen = state.load_seen()
    search_report = scholar_search.search_all_topics(topics, max_results=max_results_per_topic)

    processed = []
    skipped = []
    errors = []

    for topic_key, topic_result in search_report.items():
        if topic_result["blocked"]:
            errors.append({"topic": topic_key, "stage": "search", "error": topic_result["error"]})
            continue

        for result in topic_result["results"]:
            title, url = result["title"], result.get("scholar_url", "")

            if not scholar_search.has_public_fulltext(result):
                skipped.append({"title": title, "reason": "no public full-text link"})
                continue
            if state.is_seen(seen, title, url):
                skipped.append({"title": title, "reason": "already processed"})
                continue

            try:
                article_result = _process_article(result, dry_run=dry_run)
                processed.append(article_result)
                if not dry_run:
                    state.mark_seen(seen, title, url, extra={
                        "topic": topic_key,
                        "drive_url": article_result.get("drive_url"),
                    })
            except Exception as e:
                errors.append({
                    "title": title, "stage": "process", "error": str(e),
                    "traceback": traceback.format_exc(),
                })

    if not dry_run:
        state.save_seen(seen)

    return {
        "search_report": {k: {"count": len(v["results"]), "blocked": v["blocked"], "error": v["error"]}
                           for k, v in search_report.items()},
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
    }


def _process_article(result: dict, dry_run: bool = False) -> dict:
    title = result["title"]
    eprint_url = result["eprint_url"]
    topic_area = result["topic"]

    pdf_path = pdf_extract.download_pdf(eprint_url)
    try:
        extracted = pdf_extract.extract_text_and_figures(pdf_path)
    finally:
        # Keep the PDF around isn't necessary once text/figures are pulled out.
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

    fact_check_result = fact_check.run_fact_check(extracted["text"])
    score_result = scoring.score_article(extracted["text"], topic_area)

    document = summarizer.summarize_article(
        article_text=extracted["text"],
        figures=extracted["figures"],
        topic_area=topic_area,
        scholar_meta=result,
        score_result=score_result,
        fact_check_result=fact_check_result,
    )

    if dry_run:
        upload_result = {"uploaded": False, "drive_url": None, "docx_path": None, "error": "dry-run"}
    else:
        upload_result = drive_upload.upload_summary(
            markdown_text=document,
            figures=extracted["figures"],
            title=title or "Untitled AMRG Summary",
            work_dir=config.OUTPUT_DIR,
        )

    return {
        "title": title,
        "topic": topic_area,
        "final_writing_score": score_result["final_writing_score"],
        "page_count": extracted["page_count"],
        "figure_count": len(extracted["figures"]),
        "drive_url": upload_result.get("drive_url"),
        "docx_path": upload_result.get("docx_path"),
        "upload_error": upload_result.get("error"),
        "document_markdown": document,
    }
