"""Axis-interaction conformance for OpenType COLR v1 variable fonts.

WHAT THIS MEASURES

An OpenType ItemVariationStore may define a variation region whose peak is nonzero on
more than one axis. A delta stored against such a region contributes only when *all* of
those axes are engaged together. The contribution is therefore absent from every
single-axis view of the font, and appears only in the interior of the designspace.

Call the value of a variable attribute v(a, b) over two axes. The interaction is the
second-order mixed difference:

    I(a, b) = v(a, b) - v(a, 0) - v(0, b) + v(0, 0)

If every region has single-axis support, I is identically zero and the attribute is
additively separable: the two axes are independent and the joint behaviour is fully
predicted by the two marginals. If a joint-support region carries a nonzero delta, I is
nonzero and the joint behaviour is not predicted by either marginal.

Both are legitimate designs. This tool does not prefer one. It reports which one a given
binary actually implements, so that a claim about a font can be checked against the font
rather than taken on trust.

WHY IT MIGHT MATTER TO YOU

The OpenType specification has permitted multi-axis regions since variable fonts shipped,
and font compilers emit them routinely -- an `opsz x wght` region is ordinary. What is not
routine is *checking* them. A font can declare an axis whose every delta row is zero, and
every design application will still draw a slider for it. A font can claim a designed
interaction between two axes and ship separable deltas. Neither condition is visible
without reading the ItemVariationStore, and neither is caught by existing validators.

CHECKS

  C1  interaction identity   For every joint-support region, I(1,1) computed by evaluating
                             the store must equal the stored delta for that region, exactly.
                             This is arithmetic, not tolerance: it either holds or the
                             region model has been misunderstood.

  C2  marginal blindness     A joint delta must contribute nothing to any single-axis
                             evaluation. Verifies the interaction is absent from the
                             marginals rather than merely small in them.

  C3  zero-corner integrity  At the designspace default every region scalar is zero, so
                             every variable attribute must resolve to its static value.
                             A font failing this cannot claim its default instance matches
                             a static build.

  C4  no phantom axis        Fails a region whose every delta row is zero, and a VarData
                             whose every row is zero. An axis that moves nothing is still
                             enumerated by design tools and still offered to users as a
                             control. This is a defect with a UI.

  C5  base-layer immutability  Optional (--check-base). The topmost layer of each glyph's
                             PaintColrLayers must contain no variable paint. Where a font
                             puts an interaction on translation, this is what keeps the
                             read shape from moving; it converts "legibility is safe by
                             construction" from an assertion into a property.

The checks are independent. C1-C4 run on any COLR v1 font with a VarStore.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from itertools import combinations
from typing import Any, Iterable

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib.models import supportScalar

TOL = 1e-9


@dataclass
class Finding:
    check: str
    ok: bool
    detail: str

    def __str__(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'}  {self.check}  {self.detail}"


@dataclass
class Report:
    path: str
    axes: list[str] = field(default_factory=list)
    region_count: int = 0
    interaction_axis_pairs: list[list[str]] = field(default_factory=list)
    separable: bool = True
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    @property
    def verdict(self) -> str:
        """The sentence this binary earns. Rendered from the bytes, not written by hand."""
        if not self.findings:
            return "no COLR v1 variation store to check"
        if not self.ok:
            return "does not conform"
        if self.separable:
            return "axes are additively separable (no interaction term)"
        pairs = ", ".join("x".join(p) for p in self.interaction_axis_pairs)
        return f"carries a designed axis interaction on: {pairs}"

    def to_json(self) -> str:
        d = asdict(self)
        d["ok"] = self.ok
        d["verdict"] = self.verdict
        return json.dumps(d, indent=2)


def _supports(font: TTFont, store) -> list[dict[str, tuple[float, float, float]]]:
    """Region supports as {axisTag: (start, peak, end)}, omitting axes with peak 0.

    An axis whose peak is zero does not participate in the region's scalar, which is what
    makes a region single-axis or joint.
    """
    tags = [a.axisTag for a in font["fvar"].axes]
    out = []
    for region in store.VarRegionList.Region:
        sup = {}
        for i, axis in enumerate(region.VarRegionAxis):
            if i < len(tags) and axis.PeakCoord != 0:
                sup[tags[i]] = (axis.StartCoord, axis.PeakCoord, axis.EndCoord)
        out.append(sup)
    return out


def interaction_regions(supports: Iterable[dict]) -> list[int]:
    """Indices of regions whose peak is nonzero on two or more axes."""
    return [i for i, s in enumerate(supports) if len(s) > 1]


def _evaluate(store, supports, tags, data_index, row, loc) -> float:
    item = store.VarData[data_index].Item[row]
    total = 0.0
    for i in range(min(len(item), len(supports))):
        total += float(item[i]) * supportScalar(loc, supports[i])
    return total


def _loc(tags: list[str], **coords: float) -> dict[str, float]:
    base = {t: 0.0 for t in tags}
    base.update(coords)
    return base


def check_font(path: str, check_base: bool = False) -> Report:
    font = TTFont(path)
    report = Report(path=path)
    if "COLR" not in font or "fvar" not in font:
        return report
    colr = font["COLR"].table
    store = getattr(colr, "VarStore", None)
    if store is None:
        return report

    tags = [a.axisTag for a in font["fvar"].axes]
    supports = _supports(font, store)
    joint = interaction_regions(supports)
    report.axes = tags
    report.region_count = len(supports)
    report.interaction_axis_pairs = sorted(
        {tuple(sorted(supports[i])) for i in joint}
    )
    report.interaction_axis_pairs = [list(p) for p in report.interaction_axis_pairs]

    # C1 -- interaction identity, per joint region, per axis pair, per row.
    bad_c1: list[str] = []
    saw_interaction = False
    # Distinct axis pairs to test, not distinct regions: one pair may be covered by several
    # regions (a piecewise-split axis is stored as adjacent regions over the same pair).
    pairs = sorted({
        (a, b)
        for ri in joint
        for a, b in combinations(sorted(supports[ri]), 2)
    })
    for di, data in enumerate(store.VarData):
        for row in range(len(data.Item)):
            item = data.Item[row]
            for a, b in pairs:
                corner = _loc(tags, **{a: 1.0, b: 1.0})
                I = (
                    _evaluate(store, supports, tags, di, row, corner)
                    - _evaluate(store, supports, tags, di, row, _loc(tags, **{a: 1.0}))
                    - _evaluate(store, supports, tags, di, row, _loc(tags, **{b: 1.0}))
                    + _evaluate(store, supports, tags, di, row, _loc(tags))
                )
                # Expected: the contribution at the corner of every joint region supported
                # on exactly these axes -- SCALAR-WEIGHTED, not a raw sum. A region peaked
                # short of 1.0 contributes nothing at the corner even though its support
                # names the same pair, which is how piecewise-split axes are stored.
                expected = sum(
                    float(item[k]) * supportScalar(corner, supports[k])
                    for k in joint
                    if set(supports[k]) == {a, b} and k < len(item)
                )
                if abs(I - expected) > TOL:
                    bad_c1.append(
                        f"VarData[{di}] row {row} {a}x{b}: I(1,1)={I:g} expected {expected:g}"
                    )
                if abs(I) > TOL:
                    saw_interaction = True
    report.separable = not saw_interaction
    report.findings.append(
        Finding(
            "C1 interaction-identity",
            not bad_c1,
            "; ".join(bad_c1[:3]) if bad_c1
            else (
                f"holds on all rows; interaction "
                f"{'present' if saw_interaction else 'identically zero'}"
            ),
        )
    )

    # C2 -- marginal blindness: joint deltas must not reach any single-axis evaluation.
    bad_c2: list[str] = []
    for di, data in enumerate(store.VarData):
        for row in range(len(data.Item)):
            item = data.Item[row]
            for ri in joint:
                if ri >= len(item) or float(item[ri]) == 0:
                    continue
                for axis in supports[ri]:
                    for coord in (0.5, 1.0):
                        loc = _loc(tags, **{axis: coord})
                        full = _evaluate(store, supports, tags, di, row, loc)
                        without = sum(
                            float(item[k]) * supportScalar(loc, supports[k])
                            for k in range(min(len(item), len(supports)))
                            if k not in joint
                        )
                        if abs(full - without) > TOL:
                            bad_c2.append(
                                f"VarData[{di}] row {row}: region {ri} leaks into "
                                f"{axis}={coord} marginal"
                            )
    report.findings.append(
        Finding(
            "C2 marginal-blindness",
            not bad_c2,
            "; ".join(bad_c2[:3]) if bad_c2 else "joint deltas absent from every single-axis view",
        )
    )

    # C3 -- zero-corner integrity.
    bad_c3: list[str] = []
    for di, data in enumerate(store.VarData):
        for row in range(len(data.Item)):
            v = _evaluate(store, supports, tags, di, row, _loc(tags))
            if abs(v) > 1e-12:
                bad_c3.append(f"VarData[{di}] row {row} = {v:g} at designspace default")
    report.findings.append(
        Finding(
            "C3 zero-corner",
            not bad_c3,
            "; ".join(bad_c3[:3]) if bad_c3 else "every variable attribute resolves to its static value at the default",
        )
    )

    # C4 -- phantom axis / dead store.
    bad_c4: list[str] = []
    for di, data in enumerate(store.VarData):
        if all(all(x == 0 for x in item) for item in data.Item):
            bad_c4.append(f"VarData[{di}]: every delta row is zero")
        width = min((len(i) for i in data.Item), default=0)
        for k in range(min(width, len(supports))):
            if all(item[k] == 0 for item in data.Item):
                axes = "x".join(sorted(supports[k])) or "(no peak)"
                bad_c4.append(f"region {k} ({axes}) declared but no row uses it")
    report.findings.append(
        Finding(
            "C4 no-phantom-axis",
            not bad_c4,
            "; ".join(bad_c4[:4]) if bad_c4 else "every declared region carries at least one nonzero delta",
        )
    )

    # C5 -- base-layer immutability (opt-in).
    if check_base:
        moved = 0
        checked = 0
        layers = colr.LayerList.Paint if colr.LayerList else []
        for rec in colr.BaseGlyphList.BaseGlyphPaintRecord:
            root = rec.Paint
            if root.Format != ot.PaintFormat.PaintColrLayers:
                continue
            checked += 1
            stack = [layers[root.FirstLayerIndex + root.NumLayers - 1]]
            while stack:
                node = stack.pop()
                if getattr(node, "VarIndexBase", None) is not None:
                    moved += 1
                for attr in ("Paint", "SourcePaint", "BackdropPaint"):
                    child = getattr(node, attr, None)
                    if child is not None and hasattr(child, "Format"):
                        stack.append(child)
        report.findings.append(
            Finding(
                "C5 base-immutability",
                moved == 0,
                f"{checked} glyphs checked, {moved} variable paint(s) in a base layer",
            )
        )
    return report
