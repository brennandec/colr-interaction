"""CLI: python -m colr_interaction FONT [FONT ...]"""
from __future__ import annotations

import argparse
import sys

from .check import check_font


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="colr-interaction",
        description="Conformance checks for axis interaction in OpenType variable fonts. Reads every ItemVariationStore in the font: COLR, HVAR, VVAR, MVAR, GDEF.",
    )
    p.add_argument("fonts", nargs="+", metavar="FONT")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--top", type=int, default=20, metavar="N",
                   help="with --explain, how many terms to list (default 20)")
    p.add_argument("--check-base", action="store_true",
                   help="also run C6, base-layer immutability (COLR)")
    p.add_argument("--explain", action="store_true",
                   help="list every interaction term with its magnitude, largest first")
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
                print("  no variation store to check")
            else:
                stores = ", ".join(
                    f"{t} ({report.region_counts[t]} region"
                    f"{'' if report.region_counts[t] == 1 else 's'})"
                    for t in report.stores
                )
                print(f"  axes {report.axes}")
                print(f"  stores {stores}")
                if report.interaction_axis_sets:
                    sets = ", ".join("x".join(a) for a in report.interaction_axis_sets)
                    print(f"  interaction regions on: {sets}")
                for f in report.findings:
                    print(f"  {f}")
                for o in report.observations:
                    print(f"  note  {o}")
                if args.explain:
                    from .explain import interaction_terms
                    terms = interaction_terms(path)
                    if terms:
                        print()
                        print("  interaction terms, largest first — 'miss' is how far the")
                        print("  marginals are from the real joint value:")
                        for t in terms[:args.top]:
                            print(f"    {t.line()}")
                        if len(terms) > args.top:
                            print(f"    ... {len(terms) - args.top} more "
                                  f"(raise --top to see them)")
                    else:
                        print("  no interaction terms to explain")
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
