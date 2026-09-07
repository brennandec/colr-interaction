"""Locating and reading every ItemVariationStore in a font, correctly.

Three things here are easy to get wrong, and all three produce a confident wrong answer
rather than an error:

1. **A font has more than one variation store.** `COLR` has one; so do `HVAR`, `VVAR`,
   `MVAR` and `GDEF`. A tool that reads only `COLR` will report a font as free of axis
   interaction while `HVAR` carries a joint region that changes advance widths.

2. **Delta column != region index.** Column *i* of a `VarData` row addresses
   `VarRegionList.Region[VarData.VarRegionIndex[i]]`. An optimized font stores only the
   regions a subtable actually uses, so the identity assumption silently pairs deltas with
   the wrong regions.

3. **A delta set index is not a (subtable, row) pair until it is mapped.** A 32-bit
   `VarIdx` splits into an outer index selecting the `VarData` and an inner index selecting
   the row — and a `DeltaSetIndexMap`, when present, remaps a flat index onto that pair
   first. Reading `VarData[0].Item[n]` directly is only correct when there is one subtable
   and no map.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fontTools.ttLib import TTFont

#: Tables that may carry an ItemVariationStore, in the order a report lists them.
STORE_TABLES = ("COLR", "HVAR", "VVAR", "MVAR", "GDEF")


@dataclass
class Store:
    """One ItemVariationStore, with everything needed to evaluate it."""

    table: str
    store: object
    supports: list[dict[str, tuple[float, float, float]]] = field(default_factory=list)
    region_maps: list[list[int]] = field(default_factory=list)

    @property
    def joint_regions(self) -> list[int]:
        """Regions whose peak is nonzero on two or more axes."""
        return [i for i, s in enumerate(self.supports) if len(s) > 1]

    def columns(self, data_index: int) -> list[tuple[int, int]]:
        """(column, region index) for one VarData, resolved through VarRegionIndex."""
        return list(enumerate(self.region_maps[data_index]))


def _region_supports(store, axis_tags: list[str]) -> list[dict]:
    out = []
    for region in store.VarRegionList.Region:
        support = {}
        for i, axis in enumerate(region.VarRegionAxis):
            if i < len(axis_tags) and axis.PeakCoord != 0:
                support[axis_tags[i]] = (axis.StartCoord, axis.PeakCoord, axis.EndCoord)
        out.append(support)
    return out


def _region_map(data) -> list[int]:
    idx = getattr(data, "VarRegionIndex", None)
    if idx is not None:
        return list(idx)
    width = min((len(row) for row in data.Item), default=0)
    return list(range(width))


def var_stores(font: TTFont) -> list[Store]:
    """Every ItemVariationStore in the font, each with resolved supports and region maps."""
    if "fvar" not in font:
        return []
    axis_tags = [a.axisTag for a in font["fvar"].axes]
    found: list[Store] = []
    for tag in STORE_TABLES:
        if tag not in font:
            continue
        try:
            table = font[tag].table
        except Exception:
            continue
        store = getattr(table, "VarStore", None)
        if store is None or not getattr(store, "VarData", None):
            continue
        found.append(
            Store(
                table=tag,
                store=store,
                supports=_region_supports(store, axis_tags),
                region_maps=[_region_map(d) for d in store.VarData],
            )
        )
    return found


def resolve_var_idx(store, var_idx: int, index_map=None) -> tuple[int, int] | None:
    """A 32-bit VarIdx -> (outer, inner), through a DeltaSetIndexMap when one is present.

    Returns None when the index does not resolve to a real row, which is itself a finding:
    a paint pointing at a delta set that is not there.
    """
    if index_map is not None:
        mapping = getattr(index_map, "mapping", None)
        if mapping is not None:
            if var_idx >= len(mapping):
                return None
            var_idx = mapping[var_idx]
    outer = (var_idx >> 16) & 0xFFFF
    inner = var_idx & 0xFFFF
    if outer >= len(store.VarData):
        return None
    if inner >= len(store.VarData[outer].Item):
        return None
    return outer, inner
