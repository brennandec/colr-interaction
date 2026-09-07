"""Axis-interaction conformance for OpenType variable fonts.

WHAT THIS MEASURES

An ItemVariationStore may define a region whose peak is nonzero on more than one axis. A
delta stored against such a region contributes only when all of those axes are engaged
together. Its contribution is therefore absent from every view of the font that moves one
axis at a time, and appears only in the interior of the designspace.

For a variable value over the axes of one region, the interaction is the mixed difference
over that region's own axis set. For two axes this is the familiar

    I(a, b) = v(a, b) - v(a, 0) - v(0, b) + v(0, 0)

and for n axes it is the n-th order mixed difference, which is what isolates a genuinely
n-way term rather than the sum of its pairwise shadows.

I == 0 means the value is additively separable over those axes: they are independent, and
the joint behaviour is fully predicted by the marginals. I != 0 means it is not.

Both are legitimate designs. This tool does not prefer one. It reports which one a binary
implements, so a claim about a font can be checked against the font.

WHERE IT LOOKS

Every ItemVariationStore in the font -- COLR, HVAR, VVAR, MVAR and GDEF -- not only COLR.
A joint region in HVAR changes advance widths; reading COLR alone would call that font
free of interaction.

CHECKS

  C1  interaction-identity   Per joint region, the mixed difference evaluated from the
                             store equals that region's own contribution, exactly.
                             Evaluated at each region's PEAK VECTOR, never a fixed corner,
                             so intermediate regions, negative peaks and 3+ axis regions
                             are all covered.
  C2  marginal-blindness     A joint delta contributes nothing to any single-axis
                             evaluation -- absent from the marginals, not merely small.
  C3  zero-corner            At the designspace default every region scalar is zero, so
                             every variable value resolves to its static value.
  C4  no-phantom-axis        A declared region no delta column uses, or a VarData whose
                             every row is zero. An axis that moves nothing is still
                             enumerated by design tools and offered to users as a control.
  C5  reachable-deltas       (COLR) Every VarIndexBase in a paint resolves to a real delta
                             set, through DeltaSetIndexMap when present.
  C6  base-immutability      (COLR, opt-in) The topmost layer of each glyph carries no
                             variable paint. Where a font puts an interaction on
                             translation, this is what keeps the read shape still.

KNOWN LIMITS, stated rather than discovered later

  * avar / avar2 are not modelled. Regions are read in normalized space. An avar2 mapping
    can create axis coupling with no multi-axis region at all, and this tool will not see
    it. Reported interaction is a property of the store, not of the whole pipeline.
  * No rasterization. Rendered output is renderer-dependent and a rendered hash is a claim
    about a pinned environment, not about a font.
  * Neither presence nor absence of interaction is a spec violation. C1-C3 verify internal
    consistency and report which case holds; only C4 and C5 describe defects.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib.models import supportScalar

from .store import Store, resolve_var_idx, var_stores

TOL = 1e-9


@dataclass
class Finding:
    check: str
    ok: bool
    detail: str
    table: str = ""

    def __str__(self) -> str:
        where = f"[{self.table}] " if self.table else ""
        return f"{'PASS' if self.ok else 'FAIL'}  {self.check}  {where}{self.detail}"


@dataclass
class Report:
    path: str
    axes: list[str] = field(default_factory=list)
    stores: list[str] = field(default_factory=list)
    region_counts: dict[str, int] = field(default_factory=dict)
    interaction_axis_sets: list[list[str]] = field(default_factory=list)
    separable: bool = True
    findings: list[Finding] = field(default_factory=list)
    #: Things worth a reader's eye that are not defects. Kept separate from findings on
    #: purpose: a tool that reports every oddity as a failure trains people to ignore it.
    observations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    @property
    def verdict(self) -> str:
        """The sentence this binary earns, rendered from the bytes."""
        if not self.findings:
            return "no variation store to check"
        if not self.ok:
            return "does not conform"
        if self.separable:
            return "axes are additively separable in every variation store (no interaction term)"
        sets = ", ".join("x".join(s) for s in self.interaction_axis_sets)
        return f"carries a designed axis interaction on: {sets}"

    def to_json(self) -> str:
        d = asdict(self)
        d["ok"] = self.ok
        d["verdict"] = self.verdict
        return json.dumps(d, indent=2)


def _loc(tags: list[str], **coords: float) -> dict[str, float]:
    base = {t: 0.0 for t in tags}
    base.update(coords)
    return base


def _value(st: Store, data_index: int, row: int, loc: dict) -> float:
    item = st.store.VarData[data_index].Item[row]
    total = 0.0
    for col, region in st.columns(data_index):
        if col < len(item) and region < len(st.supports):
            total += float(item[col]) * supportScalar(loc, st.supports[region])
    return total


def _mixed_difference(st: Store, data_index: int, row: int, tags: list[str],
                      axes: list[str], peak: dict[str, float]) -> float:
    """n-th order mixed difference over `axes`, each held at its own peak or at zero."""
    total = 0.0
    for mask in range(1 << len(axes)):
        coords = {a: (peak[a] if (mask >> k) & 1 else 0.0) for k, a in enumerate(axes)}
        held_at_zero = len(axes) - bin(mask).count("1")
        total += ((-1) ** held_at_zero) * _value(st, data_index, row, _loc(tags, **coords))
    return total


def check_font(path: str, check_base: bool = False) -> Report:
    font = TTFont(path)
    report = Report(path=path)
    if "fvar" not in font:
        return report
    tags = [a.axisTag for a in font["fvar"].axes]
    report.axes = tags
    stores = var_stores(font)
    if not stores:
        return report
    report.stores = [s.table for s in stores]
    report.region_counts = {s.table: len(s.supports) for s in stores}

    axis_sets: set[tuple[str, ...]] = set()
    saw_interaction = False
    bad = {k: [] for k in ("C1", "C2", "C3", "C4")}

    for st in stores:
        for di, data in enumerate(st.store.VarData):
            cols = st.columns(di)
            joint_cols = [(c, r) for c, r in cols
                          if r < len(st.supports) and len(st.supports[r]) > 1]
            for row in range(len(data.Item)):
                item = data.Item[row]

                # C3 -- the default instance must be the static one.
                v0 = _value(st, di, row, _loc(tags))
                if abs(v0) > 1e-12:
                    bad["C3"].append(f"{st.table} VarData[{di}] row {row} = {v0:g} at the default")

                for col, ri in joint_cols:
                    if col >= len(item):
                        continue
                    axes = sorted(st.supports[ri])
                    peak = {a: st.supports[ri][a][1] for a in axes}

                    I = _mixed_difference(st, di, row, tags, axes, peak)
                    expected = sum(
                        float(item[c2]) * supportScalar(_loc(tags, **peak), st.supports[r2])
                        for c2, r2 in cols
                        if c2 < len(item) and r2 < len(st.supports)
                        and set(st.supports[r2]) == set(axes)
                    )
                    if abs(I - expected) > TOL:
                        bad["C1"].append(
                            f"{st.table} VarData[{di}] row {row} {'x'.join(axes)} at peak "
                            f"{tuple(peak[a] for a in axes)}: I={I:g} expected {expected:g}"
                        )
                    if abs(I) > TOL:
                        saw_interaction = True
                        axis_sets.add(tuple(axes))

                    # C2 -- the joint delta must not reach any single-axis evaluation.
                    if float(item[col]) == 0:
                        continue
                    for axis in axes:
                        for frac in (0.5, 1.0):
                            loc = _loc(tags, **{axis: peak[axis] * frac})
                            full = _value(st, di, row, loc)
                            without = sum(
                                float(item[c2]) * supportScalar(loc, st.supports[r2])
                                for c2, r2 in cols
                                if c2 < len(item) and r2 < len(st.supports)
                                and len(st.supports[r2]) <= 1
                            )
                            if abs(full - without) > TOL:
                                bad["C2"].append(
                                    f"{st.table} VarData[{di}] row {row}: region {ri} leaks "
                                    f"into the {axis}={peak[axis] * frac:g} marginal"
                                )



    # C4 -- a phantom axis is an fvar axis that moves NOTHING, ANYWHERE in the font.
    #
    # That is the defect worth a failure, because it is the one a user sees: every design
    # application enumerates fvar and draws a slider for it. Two narrower rules were tried
    # first and both produced false positives on shipping fonts:
    #
    #   "an all-zero VarData"        -- correct in a fixed-pitch font's HVAR, where
    #                                   advances legitimately do not vary. Flagged three
    #                                   of Apple's system fonts.
    #   "a region no subtable uses"  -- correct for a GRAD region in HVAR: a grade axis is
    #                                   defined not to change advance widths, so the
    #                                   compiler emitting the region is dead bytes, not a
    #                                   broken font. Flagged New York and SF Mono.
    #
    # Both survive as observations. Only "this axis moves nothing at all" fails, and note
    # that gvar is not read here, so an axis that drives outlines only is not reported as
    # phantom -- the check errs toward silence.
    fixed_pitch = bool(getattr(font.get("post"), "isFixedPitch", 0)) if "post" in font else False
    moves: set[str] = set()
    for st in stores:
        for di, data in enumerate(st.store.VarData):
            for col, region in st.columns(di):
                if region < len(st.supports) and any(
                    col < len(r) and r[col] != 0 for r in data.Item
                ):
                    moves.update(st.supports[region])
    if "gvar" in font:
        try:
            gvar = font["gvar"]
            for variations in list(gvar.variations.values())[:2000]:
                for v in variations:
                    for tag, (_lo, pk, _hi) in v.axes.items():
                        if pk != 0:
                            moves.add(tag)
        except Exception:
            moves.add("__gvar_unreadable__")

    # An axis whose min == max has no range to move along. Declaring one is deliberate and
    # standard -- it pins a face to a size or grade while keeping the axis present for
    # interoperability. SF Compact Italic ships opsz at 19/19/19, and an earlier cut of
    # this check called that a phantom axis. It is not a slider; there is nothing to slide.
    pinned = {a.axisTag for a in font["fvar"].axes if a.minValue == a.maxValue}
    for t in sorted(pinned):
        report.observations.append(
            f"axis {t} is pinned (min == max), so it cannot move anything and is not "
            f"checked for phantom behaviour"
        )
    silent = [t for t in tags if t not in moves and t not in pinned]
    if "__gvar_unreadable__" in moves:
        report.observations.append(
            "gvar could not be read, so an axis driving outlines only cannot be "
            "distinguished from a phantom; C4 reports nothing"
        )
    elif silent:
        bad["C4"].append(
            "axis " + ", ".join(silent) + " declared in fvar but no delta anywhere in "
            + ("gvar or " if "gvar" in font else "")
            + "+".join(report.stores) + " moves under it"
        )

    for st in stores:
        used: set[int] = set()
        for di, data in enumerate(st.store.VarData):
            for col, region in st.columns(di):
                if any(col < len(r) and r[col] != 0 for r in data.Item):
                    used.add(region)
        for ri, support in enumerate(st.supports):
            if ri not in used:
                names = "x".join(sorted(support)) or "(no peak)"
                report.observations.append(
                    f"{st.table} region {ri} ({names}) is declared but unused in that "
                    f"store -- dead bytes, not a defect"
                )
        for di, data in enumerate(st.store.VarData):
            if data.Item and all(all(x == 0 for x in r) for r in data.Item):
                note = f"{st.table} VarData[{di}] is entirely zero ({len(data.Item)} rows)"
                if st.table == "HVAR" and fixed_pitch:
                    note += " -- expected: the font is fixed-pitch, so advances do not vary"
                report.observations.append(note)

    report.separable = not saw_interaction
    report.interaction_axis_sets = [list(s) for s in sorted(axis_sets)]

    scope = "+".join(report.stores)
    report.findings.append(Finding(
        "C1 interaction-identity", not bad["C1"],
        "; ".join(bad["C1"][:3]) if bad["C1"] else
        f"holds on all rows; interaction {'present' if saw_interaction else 'identically zero'}",
        scope))
    report.findings.append(Finding(
        "C2 marginal-blindness", not bad["C2"],
        "; ".join(bad["C2"][:3]) if bad["C2"] else
        "joint deltas absent from every single-axis view", scope))
    report.findings.append(Finding(
        "C3 zero-corner", not bad["C3"],
        "; ".join(bad["C3"][:3]) if bad["C3"] else
        "every variable value resolves to its static value at the default", scope))
    report.findings.append(Finding(
        "C4 no-phantom-axis", not bad["C4"],
        "; ".join(bad["C4"][:4]) if bad["C4"] else
        "every fvar axis moves something", scope))

    # C5 -- every VarIndexBase in COLR resolves to a real delta set.
    colr_store = next((s for s in stores if s.table == "COLR"), None)
    if colr_store is not None and "COLR" in font:
        colr = font["COLR"].table
        index_map = getattr(colr, "VarIndexMap", None)
        unresolved, checked = [], 0
        layers = colr.LayerList.Paint if colr.LayerList else []
        seen: set[int] = set()
        for paint in layers:
            stack = [paint]
            while stack:
                node = stack.pop()
                vib = getattr(node, "VarIndexBase", None)
                if vib is not None and vib not in seen:
                    seen.add(vib)
                    checked += 1
                    if resolve_var_idx(colr_store.store, vib, index_map) is None:
                        unresolved.append(str(vib))
                for attr in ("Paint", "SourcePaint", "BackdropPaint"):
                    child = getattr(node, attr, None)
                    if child is not None and hasattr(child, "Format"):
                        stack.append(child)
        report.findings.append(Finding(
            "C5 reachable-deltas", not unresolved,
            f"{checked} distinct VarIndexBase resolved"
            + (f"; unresolved: {', '.join(unresolved[:5])}" if unresolved else "")
            + (" (via DeltaSetIndexMap)" if index_map is not None else ""),
            "COLR"))

    # C6 -- base-layer immutability (opt-in, COLR).
    if check_base and "COLR" in font:
        colr = font["COLR"].table
        layers = colr.LayerList.Paint if colr.LayerList else []
        moved = checked = 0
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
        report.findings.append(Finding(
            "C6 base-immutability", moved == 0,
            f"{checked} glyphs checked, {moved} variable paint(s) in a base layer", "COLR"))

    return report
