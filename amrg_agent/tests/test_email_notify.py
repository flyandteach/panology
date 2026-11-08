import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents import email_notify


def _report(**overrides):
    base = {
        "search_report": {"AAM": {"count": 3, "blocked": False, "error": None}},
        "processed": [],
        "skipped": [],
        "errors": [],
    }
    base.update(overrides)
    return base


def test_subject_reflects_zero_new_articles():
    subject, body = email_notify.build_digest(_report())
    assert "no new articles" in subject.lower()
    assert "0 new article" in body.lower()


def test_subject_and_body_list_processed_articles():
    report = _report(processed=[{
        "title": "eVTOL Noise Modeling", "topic": "eVTOL",
        "final_writing_score": 7.5, "figure_count": 3,
        "drive_url": "https://drive.google.com/doc123",
    }])
    subject, body = email_notify.build_digest(report)
    assert "1 new article" in subject
    assert "eVTOL Noise Modeling" in body
    assert "https://drive.google.com/doc123" in body
    assert "7.5" in body


def test_body_flags_blocked_topics():
    report = _report(search_report={"UAM": {"count": 0, "blocked": True, "error": "captcha"}})
    _, body = email_notify.build_digest(report)
    assert "BLOCKED" in body


def test_body_lists_errors():
    report = _report(errors=[{"stage": "process", "title": "Bad PDF", "error": "could not parse"}])
    _, body = email_notify.build_digest(report)
    assert "Bad PDF" in body
    assert "could not parse" in body


def test_send_digest_without_credentials_reports_not_sent(monkeypatch):
    monkeypatch.delenv("EMAIL_SMTP_USER", raising=False)
    monkeypatch.delenv("EMAIL_SMTP_PASSWORD", raising=False)
    result = email_notify.send_digest(_report())
    assert result["sent"] is False
    assert "not configured" in result["error"]
