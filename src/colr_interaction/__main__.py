"""CLI: python -m colr_interaction FONT [FONT ...]"""
from __future__ import annotations

import argparse
import sys

from .check import check_font


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="colr-interaction",
        description="Conformance checks for axis interaction in OpenType COLR v1 variable fonts.",
    )
    p.add_argument("fonts", nargs="+", metavar="FONT")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--check-base", action="store_true",
                   help="also run C5, base-layer immutability")
    p.add_argument("--require-interaction", action="store_true",
                   help="exit non-zero if the font is additively separable; use on a build "
                        "that claims a designed interaction")
    args = p.parse_args(argv)

    worst = 0
    for path in args.fonts:
        try:
            report = check_font(path, check_base=args.check_base)
        except Exception as exc:  # unreadable font is a usage error, not a failed check
            print(f"{path}: cannot read ({exc})", file=sys.stderr)
            worst = max(worst, 2)
            continue

        if args.json:
            print(report.to_json())
        else:
            print(path)
            if not report.findings:
                print("  no COLR v1 variation store to check")
            else:
                print(f"  axes {report.axes}  regions {report.region_count}")
                if report.interaction_axis_pairs:
                    pairs = ", ".join("x".join(p) for p in report.interaction_axis_pairs)
                    print(f"  interaction regions on: {pairs}")
                for f in report.findings:
                    print(f"  {f}")
            print(f"  -> {report.verdict}")
            print()

        if not report.ok:
            worst = max(worst, 1)
        elif args.require_interaction and report.separable:
            print(f"{path}: --require-interaction set but the font is additively separable",
                  file=sys.stderr)
            worst = max(worst, 1)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
