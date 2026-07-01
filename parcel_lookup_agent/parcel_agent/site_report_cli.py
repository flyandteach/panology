"""CLI: extract a location from a PDF and report the nearest public-use airport(s).

    python -m parcel_agent.site_report_cli --pdf report.pdf
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .site_report import SiteReportAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="Path to a PDF file")
    parser.add_argument("--n-airports", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    agent = SiteReportAgent(n_airports=args.n_airports, timeout=args.timeout)
    report = agent.run_from_pdf(args.pdf)

    if args.json:
        print(json.dumps(dataclasses.asdict(report), indent=2, default=str))
        return 0 if report.found else 1

    print(f"PDF: {args.pdf}")
    if report.extracted:
        print(f"  Address found:     {report.extracted.address}")
        print(f"  PLSS found:        {report.extracted.plss.raw_text if report.extracted.plss else None}")
        print(f"  Parcel # found:    {report.extracted.apn}")
        print(f"  County/state hint: {report.extracted.county_hint}, {report.extracted.state_hint}")
    print()

    if not report.found:
        print(f"COULD NOT RESOLVE LOCATION: {report.error}")
    else:
        print(f"Resolved location: ({report.lat}, {report.lon}) via {report.location_source} "
              f"[{report.location_confidence}]")
        if report.parcel and report.parcel.found:
            print(f"  Parcel APN: {report.parcel.apn}, owner: {report.parcel.owner_name}")
        else:
            print("  No parcel verified at this location.")
        print()
        if not report.airport_data_is_public_use_verified:
            print("  NOTE: airport dataset is a fallback source, NOT verified public-use-only.")
            print("        Run `python -m parcel_agent.airports_refresh` for verified FAA data.")
        print("  Nearest airports:")
        for airport in report.nearest_airports:
            print(f"    {airport.ident:6s} {airport.name:40s} "
                  f"{airport.distance_nm:8.2f} nm  {airport.distance_mi:8.2f} mi")

    print("\nAttempts:")
    for attempt in report.attempts:
        status = "ok" if attempt.success else "--"
        print(f"  [{status}] {attempt.strategy}: {attempt.detail}")

    return 0 if report.found else 1


if __name__ == "__main__":
    sys.exit(main())
