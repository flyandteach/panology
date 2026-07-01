"""Command-line entry point: python -m parcel_agent.cli --address "..."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .agent import ParcelLookupAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Look up a US parcel by street address.")
    parser.add_argument("--address", required=True, help="Street address to look up")
    parser.add_argument("--timeout", type=int, default=20, help="Per-request timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a summary")
    args = parser.parse_args(argv)

    agent = ParcelLookupAgent(timeout=args.timeout)
    result = agent.lookup(args.address)

    if args.json:
        print(json.dumps(dataclasses.asdict(result), indent=2, default=str))
        return 0 if result.found else 1

    print(f"Address: {args.address}")
    if result.geocode:
        print(f"Geocoded: {result.geocode.matched_address or result.geocode.input_address} "
              f"({result.geocode.lat}, {result.geocode.lon}) via {result.geocode.source}")
        print(f"County: {result.county_name}, {result.state_abbr} (FIPS {result.geocode.county_fips})")

    print()
    if result.found:
        print(f"PARCEL FOUND  [confidence: {result.confidence}, strategy: {result.strategy_used}]")
        print(f"  APN:              {result.apn}")
        print(f"  Owner:            {result.owner_name}")
        print(f"  Situs address:    {result.situs_address}")
        print(f"  Acres:            {result.area_acres}")
        print(f"  Source service:   {result.source_service}")
        print(f"  Source layer:     {result.source_layer_name}")
    else:
        print("NO PARCEL FOUND")
        print(f"  {result.error}")

    print("\nAttempts:")
    for attempt in result.attempts:
        status = "ok" if attempt.success else "--"
        print(f"  [{status}] {attempt.strategy}: {attempt.detail}")

    return 0 if result.found else 1


if __name__ == "__main__":
    sys.exit(main())
