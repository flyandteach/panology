"""Notification channels for status changes/failures. Each channel is
opt-in via environment variables so the tool works with zero config
(console-only) and gains channels as you set secrets/env vars for it.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText

import requests


@dataclass
class Change:
    asn: str
    label: str
    old_status: str | None
    new_status: str
    is_terminal: bool


@dataclass
class Failure:
    asn: str
    label: str
    error: str
    consecutive_failures: int


def format_message(changes: list[Change], failures: list[Failure]) -> str:
    lines = []
    if changes:
        lines.append("FAA 7460 obstruction case status changes:")
        for c in changes:
            marker = "DETERMINATION ISSUED" if c.is_terminal else "status update"
            old = c.old_status or "(new)"
            lines.append(f"  [{marker}] {c.asn} — {c.label}: {old} -> {c.new_status}")
            lines.append(
                "    Look up full details at https://oeaaa.faa.gov/ "
                f"(search for ASN {c.asn})"
            )
    if failures:
        if lines:
            lines.append("")
        lines.append("Checks that failed (tool may need attention):")
        for f in failures:
            lines.append(
                f"  {f.asn} — {f.label}: {f.error} "
                f"(failed {f.consecutive_failures}x in a row)"
            )
    return "\n".join(lines)


def notify_console(message: str) -> None:
    print(message)


def notify_email(message: str, subject: str) -> None:
    host = os.environ.get("SMTP_HOST")
    to_addr = os.environ.get("NOTIFY_EMAIL_TO")
    if not host or not to_addr:
        return
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    from_addr = os.environ.get("NOTIFY_EMAIL_FROM", user or to_addr)

    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())


def notify_webhook(message: str) -> None:
    url = os.environ.get("NOTIFY_WEBHOOK_URL")
    if not url:
        return
    fmt = os.environ.get("NOTIFY_WEBHOOK_FORMAT", "plain").lower()
    if fmt == "slack" or fmt == "discord":
        payload = {"text": message}
    else:
        payload = {"message": message}
    requests.post(url, json=payload, timeout=20)


def notify_github_issue(message: str, subject: str) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return
    api = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    search = requests.get(
        api,
        headers=headers,
        params={"state": "open", "labels": "faa-7460-tracker"},
        timeout=20,
    )
    search.raise_for_status()
    existing = next(
        (i for i in search.json() if i["title"] == subject), None
    )

    if existing:
        requests.post(
            f"{api}/{existing['number']}/comments",
            headers=headers,
            json={"body": message},
            timeout=20,
        ).raise_for_status()
    else:
        requests.post(
            api,
            headers=headers,
            json={"title": subject, "body": message, "labels": ["faa-7460-tracker"]},
            timeout=20,
        ).raise_for_status()


def notify_all(changes: list[Change], failures: list[Failure]) -> None:
    if not changes and not failures:
        return
    message = format_message(changes, failures)
    subject = "FAA 7460 obstruction case status update"
    if any(c.is_terminal for c in changes):
        subject = "FAA determination issued — 7460 obstruction case(s)"

    notify_console(message)
    notify_email(message, subject)
    notify_webhook(message)
    notify_github_issue(message, subject)
