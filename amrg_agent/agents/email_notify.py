"""
Weekly digest email.

Default transport is plain SMTP against Gmail (smtp.gmail.com:587 + STARTTLS)
using a Gmail App Password -- this needs no new third-party account, just
2FA enabled on the sending Gmail account and an App Password generated at
https://myaccount.google.com/apppasswords. See config.py for the env vars.

Sends a digest on every run (including "nothing new this week"), so a
missed/blocked run is visible rather than silent.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

import config


def build_digest(report: dict) -> tuple:
    """Build (subject, plain_text_body) from a pipeline run report."""
    processed = report.get("processed", [])
    skipped = report.get("skipped", [])
    errors = report.get("errors", [])
    search_report = report.get("search_report", {})

    if processed:
        subject = f"AMRG weekly digest: {len(processed)} new article(s)"
    else:
        subject = "AMRG weekly digest: no new articles this week"

    lines = [f"AMRG weekly literature watch -- {len(processed)} new article(s) processed.", ""]

    if processed:
        lines.append("New articles:")
        for a in processed:
            link = a.get("drive_url") or a.get("docx_path") or "(no link available)"
            lines.append(f"- {a.get('title') or 'Untitled'} [{a.get('topic', '?')}]")
            lines.append(f"    Final Writing Score: {a.get('final_writing_score', 'n/a')}")
            lines.append(f"    Figures extracted: {a.get('figure_count', 0)}")
            lines.append(f"    {link}")
        lines.append("")
    else:
        lines.append("No new articles with a public full-text link were found this run.")
        lines.append("")

    lines.append("Search coverage by topic:")
    for topic, info in search_report.items():
        status = "BLOCKED (Scholar likely rate-limited this run)" if info.get("blocked") else "ok"
        lines.append(f"- {topic}: {info.get('count', 0)} hit(s) -- {status}")
    lines.append("")

    if skipped:
        already_seen = sum(1 for s in skipped if s.get("reason") == "already processed")
        no_fulltext = sum(1 for s in skipped if s.get("reason") == "no public full-text link")
        lines.append(f"Skipped: {already_seen} already processed, {no_fulltext} with no public full-text link.")
        lines.append("")

    if errors:
        lines.append(f"{len(errors)} error(s) this run:")
        for e in errors:
            lines.append(f"- [{e.get('stage', '?')}] {e.get('title') or e.get('topic')}: {e.get('error')}")
        lines.append("")

    lines.append(
        "Reminder: Google Scholar scraping is best-effort and has no official API, so a "
        "blocked topic above just means try again next week. Fact-check coverage is "
        "heuristic (Crossref reference lookup + LLM claim-plausibility check) -- "
        "plagiarism-overlap and AI-authorship detection are intentionally not included."
    )

    return subject, "\n".join(lines)


def send_digest(report: dict) -> dict:
    """Send the weekly digest. Returns {"sent": bool, "error": str|None}."""
    smtp_user = os.environ.get("EMAIL_SMTP_USER")
    smtp_password = os.environ.get("EMAIL_SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        return {
            "sent": False,
            "error": "EMAIL_SMTP_USER/EMAIL_SMTP_PASSWORD not configured; digest not sent.",
        }

    recipients = [addr.strip() for addr in config.EMAIL_TO.split(",") if addr.strip()]
    if not recipients:
        return {"sent": False, "error": "EMAIL_TO resolved to no recipients."}

    subject, body = build_digest(report)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(config.EMAIL_SMTP_HOST, config.EMAIL_SMTP_PORT, timeout=config.REQUEST_TIMEOUT) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return {"sent": True, "error": None}
    except Exception as e:
        return {"sent": False, "error": str(e)}
