"""
Weekly Aviation Futures Intelligence email report.
Run directly or via Windows Task Scheduler.
"""

import os
import sys
import json
import smtplib
import argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(__file__))
from agent import AviationFuturesAgent, HORIZON_LABELS


# ---------------------------------------------------------------------------
# Configuration — override via environment variables or command-line args
# ---------------------------------------------------------------------------

DEFAULT_TO      = os.environ.get("REPORT_TO",       "flyandteach@gmail.com")
DEFAULT_FROM    = os.environ.get("REPORT_FROM",      "flyandteach@gmail.com")
DEFAULT_HORIZON = os.environ.get("REPORT_HORIZON",   "mid")
GMAIL_APP_PASS  = os.environ.get("GMAIL_APP_PASSWORD", "")


# ---------------------------------------------------------------------------
# HTML formatter
# ---------------------------------------------------------------------------

def _bar(value: float, colour: str = "#4f8ef7") -> str:
    pct = int(value * 100)
    return (
        f'<div style="background:#e8e8e8;border-radius:4px;height:10px;width:200px;display:inline-block;vertical-align:middle">'
        f'<div style="background:{colour};width:{pct}%;height:100%;border-radius:4px"></div></div>'
        f' <span style="font-size:12px;color:#555">{pct}%</span>'
    )


def _direction_badge(direction: str) -> str:
    colours = {
        "accelerating": ("#e6f4ea", "#2d7a3a"),
        "maturing":     ("#e8f0fe", "#1a56cc"),
        "steady":       ("#fef9e7", "#b7840a"),
        "decelerating": ("#fce8e6", "#c5221f"),
        "reversing":    ("#fce8e6", "#c5221f"),
    }
    bg, fg = colours.get(direction, ("#f1f3f4", "#444"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:12px;'
        f'font-size:12px;font-weight:600">{direction}</span>'
    )


def build_html(result: dict) -> str:
    horizon_label = HORIZON_LABELS.get(result.get("horizon", "mid"), "Mid-term (3–7 years)")
    generated = result.get("generated_at", datetime.utcnow().isoformat())[:10]

    # --- header ---
    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a1a;
         max-width: 760px; margin: 0 auto; padding: 24px; background: #fff; }}
  h1   {{ font-size: 22px; color: #0d1b2a; margin-bottom: 4px; }}
  h2   {{ font-size: 16px; color: #1a3a5c; border-bottom: 2px solid #d0e4ff;
         padding-bottom: 6px; margin-top: 32px; }}
  h3   {{ font-size: 14px; color: #1a3a5c; margin: 20px 0 6px; }}
  p    {{ line-height: 1.6; font-size: 14px; color: #333; }}
  .meta {{ font-size: 12px; color: #888; margin-bottom: 24px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th    {{ background: #f0f4ff; padding: 8px 10px; text-align: left; color: #1a3a5c; }}
  td    {{ padding: 8px 10px; border-bottom: 1px solid #eee; vertical-align: middle; }}
  .rec  {{ background: #f8faff; border-left: 3px solid #4f8ef7; padding: 8px 12px;
           margin: 6px 0; font-size: 13px; }}
  .theme {{ background: #fffbf0; border-left: 3px solid #f4a800; padding: 8px 12px;
            margin: 6px 0; font-size: 13px; }}
  .high   {{ color: #c5221f; font-weight: 600; }}
  .medium {{ color: #b7840a; font-weight: 600; }}
  .low    {{ color: #888; }}
  .footer {{ font-size: 11px; color: #aaa; margin-top: 40px; border-top: 1px solid #eee;
             padding-top: 12px; }}
</style>
</head>
<body>
<h1>✈ Aviation Futures Intelligence</h1>
<div class="meta">Weekly report · {horizon_label} · {generated}</div>
"""

    # --- executive summary ---
    summary = result.get("executive_summary", "")
    if summary:
        html += f"<h2>Executive Summary</h2><p>{summary}</p>"

    # --- domain table ---
    domains = result.get("domains", {})
    if domains:
        html += """
<h2>Domain Overview</h2>
<table>
<tr>
  <th>Domain</th>
  <th>Signal</th>
  <th>Direction</th>
  <th>Adoption</th>
  <th>Infrastructure</th>
</tr>"""
        for dname, d in domains.items():
            adoption = d.get("adoption_probability_score")
            infra    = d.get("infrastructure_readiness")
            signal   = d.get("signal_strength", 0)
            direction = d.get("trend_direction", "—")
            html += f"""
<tr>
  <td><strong>{dname}</strong></td>
  <td>{signal:.1f}/10</td>
  <td>{_direction_badge(direction)}</td>
  <td>{"&nbsp;" + _bar(adoption) if adoption is not None else "—"}</td>
  <td>{"&nbsp;" + _bar(infra, "#34a853") if infra is not None else "—"}</td>
</tr>"""
        html += "</table>"

        # domain details
        for dname, d in domains.items():
            html += f"<h3>{dname}</h3>"
            devs = d.get("key_developments", [])
            if devs:
                html += "<p><strong>Key Developments</strong></p><ul>"
                for dev in devs:
                    html += f"<li style='font-size:13px;margin-bottom:4px'>{dev}</li>"
                html += "</ul>"
            gaps = d.get("infrastructure_gaps", [])
            if gaps:
                html += "<p><strong>Infrastructure Gaps</strong></p><ul>"
                for g in gaps:
                    html += f"<li style='font-size:13px;color:#c5221f;margin-bottom:4px'>{g}</li>"
                html += "</ul>"
            signals = d.get("watch_signals", [])
            if signals:
                html += "<p><strong>Watch Signals</strong></p><ul>"
                for s in signals:
                    html += f"<li style='font-size:13px;color:#1a56cc;margin-bottom:4px'>→ {s}</li>"
                html += "</ul>"

    # --- cross-domain themes ---
    themes = result.get("cross_domain_themes", [])
    if themes:
        html += "<h2>Cross-Domain Themes</h2>"
        for t in themes:
            urgency = t.get("urgency", "low")
            html += (
                f'<div class="theme">'
                f'<strong>{t["theme"]}</strong> '
                f'<span class="{urgency}">({urgency} urgency)</span><br>'
                f'<span style="font-size:13px">{t["description"]}</span><br>'
                f'<span style="font-size:12px;color:#888">Affects: {", ".join(t.get("affected_domains", []))}</span>'
                f'</div>'
            )

    # --- scenario flags ---
    flags = result.get("scenario_flags", [])
    if flags:
        html += "<h2>Scenario Flags</h2><table><tr><th>Scenario</th><th>Probability</th><th>Impact</th></tr>"
        for f in flags:
            prob = f.get("probability", 0)
            html += f"<tr><td><strong>{f['scenario']}</strong></td><td>{prob:.0%}</td><td style='font-size:13px'>{f.get('impact','—')}</td></tr>"
        html += "</table>"

    # --- recommendations ---
    recs = result.get("top_recommendations", [])
    if recs:
        html += "<h2>Top Recommendations</h2>"
        for i, r in enumerate(recs, 1):
            html += f'<div class="rec"><strong>{i}.</strong> {r}</div>'

    html += """
<div class="footer">
  Aviation Futures Intelligence · Generated automatically · Powered by Claude<br>
  To stop receiving these reports, delete the scheduled task in Windows Task Scheduler.
</div>
</body></html>"""

    return html


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

def send_report(to: str, from_addr: str, app_password: str, horizon: str = "mid"):
    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD is not set. Add it to launch_weekly.bat.")
        sys.exit(1)

    print(f"Generating {HORIZON_LABELS.get(horizon, horizon)} forecast…")
    agent = AviationFuturesAgent()
    result = agent.run_forecast(horizon=horizon)

    html_body = build_html(result)
    today = datetime.utcnow().strftime("%b %d, %Y")
    subject = f"Aviation Futures Intelligence — Weekly Brief ({today})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html"))

    print(f"Sending to {to}…")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_addr, app_password)
        server.sendmail(from_addr, to, msg.as_string())

    print("Report sent successfully.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send weekly Aviation Futures email report.")
    parser.add_argument("--to",       default=DEFAULT_TO)
    parser.add_argument("--horizon",  default=DEFAULT_HORIZON, choices=["near", "mid", "far"])
    args = parser.parse_args()

    send_report(
        to=args.to,
        from_addr=DEFAULT_FROM,
        app_password=GMAIL_APP_PASS,
        horizon=args.horizon,
    )
