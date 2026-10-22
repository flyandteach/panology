"""Command line: evaluate a hub from a JSON inputs file and write a report.

    python -m hub.cli examples/suburban_store.json --svg layout.svg
"""

from __future__ import annotations

import argparse
import json
import sys

from .design import compare_with_baseline
from .models import HubInputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="?", help="JSON file of inputs (omit to use defaults)")
    parser.add_argument("--svg", help="write the proposed layout to this SVG file")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    data = {}
    if args.inputs:
        with open(args.inputs) as f:
            data = json.load(f)
    proposed, baseline = compare_with_baseline(HubInputs.from_dict(data))

    if args.svg:
        with open(args.svg, "w") as f:
            f.write(proposed.layout.to_svg())

    if args.json:
        json.dump({"proposed": proposed.summary(), "baseline": baseline.summary()}, sys.stdout, indent=2)
        print()
        return 0

    cap = proposed.capacity
    print(f"Peak sorties/h {cap.sorties_per_hour:.0f} | aircraft {cap.aircraft_required} | pads {cap.pads_required} "
          f"| packs {cap.batteries_required} | charging slots {cap.charging_slots} "
          f"| peak power {proposed.peak_power_kw:.0f} kW")
    print(f"Footprint {proposed.layout.required_w:.0f} x {proposed.layout.required_d:.0f} m "
          f"({'fits' if proposed.layout.fits else 'DOES NOT FIT'} the site)")
    print(f"\n{'Category':<12}{'Proposed':>10}{'Baseline':>10}")
    for cat, score in proposed.scores().items():
        print(f"{cat:<12}{score:>10.0%}{baseline.scores()[cat]:>10.0%}")
    print("\nOpen items in the proposed design:")
    failed = [c for c in proposed.checks if not c.passed]
    for c in failed:
        print(f"  [{c.category}] {c.name}: {c.detail}")
    for flag in proposed.fire.flags:
        print(f"  [Fire] {flag}")
    if not failed and not proposed.fire.flags:
        print("  none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
