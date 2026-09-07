"""Build the three fixture fonts from scratch. No third-party font data is vendored.

  separable.ttf    two single-axis regions            -> I identically zero
  interacting.ttf  adds a joint region with a delta   -> I equals that delta
  phantom.ttf      declares a region with no deltas   -> C4 fails
"""
from __future__ import annotations

import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.misc.fixedTools import floatToFixed
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.colorLib.builder import buildCPAL
from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore

HERE = Path(__file__).resolve().parent / "fixtures"
AXES = [("AAAA", 0.0, 0.0, 100.0, "Alpha Axis"),
        ("BBBB", 0.0, 0.0, 100.0, "Beta Axis"),
        ("CCCC", -100.0, 0.0, 100.0, "Gamma Axis")]
GLYPHS = [".notdef", "A"]


def _square(pen_box=(100, 0, 500, 700)):
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    pen = TTGlyphPen(None)
    x0, y0, x1, y1 = pen_box
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0)); pen.lineTo((x1, y1)); pen.lineTo((x0, y1))
    pen.closePath()
    return pen.glyph()


def build(name: str, regions, items, region_index=None):
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(GLYPHS)
    fb.setupCharacterMap({0x41: "A"})
    fb.setupGlyf({g: _square() for g in GLYPHS})
    fb.setupHorizontalMetrics({g: (600, 100) for g in GLYPHS})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": f"ColrInteraction {name}", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.setupFvar([(t, lo, d, hi, n) for t, lo, d, hi, n in AXES], [])

    font = fb.font
    font["CPAL"] = buildCPAL([[(0, 0, 0, 1.0), (1, 1, 1, 1.0)]])

    fill = ot.Paint()
    fill.Format = ot.PaintFormat.PaintVarSolid
    fill.PaletteIndex = 0
    fill.Alpha = 0.0
    fill.VarIndexBase = 0

    glyph_paint = ot.Paint()
    glyph_paint.Format = ot.PaintFormat.PaintGlyph
    glyph_paint.Glyph = "A"
    glyph_paint.Paint = fill

    base = ot.Paint()
    base.Format = ot.PaintFormat.PaintGlyph
    base.Glyph = "A"
    solid = ot.Paint()
    solid.Format = ot.PaintFormat.PaintSolid
    solid.PaletteIndex = 1
    solid.Alpha = 1.0
    base.Paint = solid

    root = ot.Paint()
    root.Format = ot.PaintFormat.PaintColrLayers
    root.FirstLayerIndex = 0
    root.NumLayers = 2

    rec = ot.BaseGlyphPaintRecord()
    rec.BaseGlyph = "A"
    rec.Paint = root

    table = ot.COLR()
    table.Version = 1
    table.BaseGlyphList = ot.BaseGlyphList()
    table.BaseGlyphList.BaseGlyphPaintRecord = [rec]
    table.BaseGlyphList.BaseGlyphCount = 1
    table.LayerList = ot.LayerList()
    table.LayerList.Paint = [glyph_paint, base]
    table.LayerList.LayerCount = 2
    table.ClipList = None
    table.VarIndexMap = None
    tags = [a[0] for a in AXES]
    ri = region_index if region_index is not None else list(range(len(regions)))
    table.VarStore = buildVarStore(
        buildVarRegionList(regions, tags),
        [buildVarData(ri, items, optimize=False)],
    )
    colr = newTable("COLR")
    colr.table = table
    font["COLR"] = colr

    HERE.mkdir(parents=True, exist_ok=True)
    out = HERE / f"{name}.ttf"
    font.save(out)
    print(f"  {out.name}")


A = floatToFixed(0.30, 14)
B = floatToFixed(0.20, 14)
J = floatToFixed(0.05, 14)

if __name__ == "__main__":
    print("building fixtures:")
    build("separable",
          [{"AAAA": (0.0, 1.0, 1.0)}, {"BBBB": (0.0, 1.0, 1.0)}],
          [[A, B]])
    build("interacting",
          [{"AAAA": (0.0, 1.0, 1.0)}, {"BBBB": (0.0, 1.0, 1.0)},
           {"AAAA": (0.0, 1.0, 1.0), "BBBB": (0.0, 1.0, 1.0)}],
          [[A, B, J]])
    build("phantom",
          [{"AAAA": (0.0, 1.0, 1.0)}, {"BBBB": (0.0, 1.0, 1.0)}],
          [[A, 0]])

    # Column order deliberately NOT the region order. A tool that treats delta column i as
    # Region[i] pairs every delta with the wrong region here and still "passes" quietly.
    build("shuffled-regions",
          [{"AAAA": (0.0, 1.0, 1.0)},
           {"BBBB": (0.0, 1.0, 1.0)},
           {"AAAA": (0.0, 1.0, 1.0), "BBBB": (0.0, 1.0, 1.0)}],
          [[J, B, A]],
          region_index=[2, 1, 0])

    # Intermediate joint region: start < peak < end, peak well short of 1.0. Sampling the
    # +1 corner gives scalar 0 and reports "no interaction" on a font that has one.
    build("intermediate-peak",
          [{"AAAA": (0.0, 1.0, 1.0)},
           {"BBBB": (0.0, 1.0, 1.0)},
           {"AAAA": (0.0, 0.5, 0.75), "BBBB": (0.0, 0.5, 0.75)}],
          [[A, B, J]])

    # Negative peak on a bipolar axis, joint with a positive one.
    build("negative-peak",
          [{"AAAA": (0.0, 1.0, 1.0)},
           {"CCCC": (-1.0, -1.0, 0.0)},
           {"AAAA": (0.0, 1.0, 1.0), "CCCC": (-1.0, -1.0, 0.0)}],
          [[A, B, J]])

    # Three-way region: no pair of axes alone explains it.
    build("three-way",
          [{"AAAA": (0.0, 1.0, 1.0)},
           {"BBBB": (0.0, 1.0, 1.0)},
           {"AAAA": (0.0, 1.0, 1.0), "BBBB": (0.0, 1.0, 1.0), "CCCC": (0.0, 1.0, 1.0)}],
          [[A, B, J]])
    sys.exit(0)
