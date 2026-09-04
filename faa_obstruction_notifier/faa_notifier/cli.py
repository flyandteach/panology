"""Command-line entrypoint. Checks every ASN in the watchlist, compares
against the last known state, notifies on changes/failures, and persists
the new state.

Usage:
    python -m faa_notifier.cli check
    python -m faa_notifier.cli selftest 2026-ANM-456-OE
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

from . import checker, notify

DEFAULT_WATCHLIST = Path(__file__).resolve().parent.parent / "watchlist.json"
DEFAULT_STATE = Path(__file__).resolve().parent.parent / "state.json"

FAILURE_STREAK_TO_ALERT = 3


def load_watchlist(path: Path) -> list[dict]:
    with path.open() as f:
        return json.load(f)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def run_check(watchlist_path: Path, state_path: Path) -> int:
    watchlist = load_watchlist(watchlist_path)
    state = load_state(state_path)

    changes: list[notify.Change] = []
    failures: list[notify.Failure] = []
    session = requests.Session()

    for entry in watchlist:
        asn = entry["asn"]
        label = entry.get("label", asn)
        prior = state.get(asn, {})

        result = checker.fetch_case_status(asn, session=session)

        if not result.ok:
            streak = prior.get("consecutive_failures", 0) + 1
            state.setdefault(asn, {})
            state[asn]["consecutive_failures"] = streak
            state[asn]["last_error"] = result.error
            state[asn]["last_checked"] = result.checked_at
            print(
                f"[WARN] {asn}: check failed ({streak}x in a row): {result.error}"
            )
            if result.debug_body_snippet is not None:
                print(
                    f"        http_status={result.debug_http_status} "
                    f"content_type={result.debug_content_type!r}"
                )
                print(f"        body_snippet={result.debug_body_snippet!r}")
            if streak >= FAILURE_STREAK_TO_ALERT:
                failures.append(
                    notify.Failure(
                        asn=asn, label=label, error=result.error, consecutive_failures=streak
                    )
                )
            continue

        prior_status = prior.get("status")
        history = prior.get("history", [])

        if prior_status is not None and prior_status != result.status:
            changes.append(
                notify.Change(
                    asn=asn,
                    label=label,
                    old_status=prior_status,
                    new_status=result.status,
                    is_terminal=checker.is_terminal(result.status),
                )
            )

        if prior_status != result.status:
            history = history + [
                {"status": result.status, "observed": result.checked_at}
            ]

        state[asn] = {
            "status": result.status,
            "last_checked": result.checked_at,
            "consecutive_failures": 0,
            "history": history,
        }

    save_state(state_path, state)
    notify.notify_all(changes, failures)

    ok_count = sum(1 for e in watchlist if state.get(e["asn"], {}).get("consecutive_failures") == 0)
    if not changes and ok_count == len(watchlist):
        print(f"Checked {len(watchlist)} case(s), no status changes.")
    else:
        print(
            f"Checked {len(watchlist)} case(s): {ok_count} ok, "
            f"{len(watchlist) - ok_count} failing, {len(changes)} changed."
        )

    return 0


def run_selftest(asn: str) -> int:
    result = checker.fetch_case_status(asn)
    print(f"asn={result.asn} ok={result.ok} status={result.status} error={result.error}")
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FAA 7460 obstruction case notifier")
    sub = parser.add_subparsers(dest="command", required=True)

    check_p = sub.add_parser("check", help="Check all ASNs in the watchlist once")
    check_p.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    check_p.add_argument("--state", type=Path, default=DEFAULT_STATE)

    selftest_p = sub.add_parser(
        "selftest", help="Fetch one ASN and print the raw parsed result (no state/notify)"
    )
    selftest_p.add_argument("asn")

    args = parser.parse_args(argv)

    if args.command == "check":
        return run_check(args.watchlist, args.state)
    if args.command == "selftest":
        return run_selftest(args.asn)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
