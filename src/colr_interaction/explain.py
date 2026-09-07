"""Report WHAT interacts and by how much, not only whether anything does.

A pass/fail verdict tells you a font has a joint region. It does not tell you that the
advance width of one glyph moves twelve units only when optical size and weight are both
engaged, which is the thing a type designer can act on.

For each joint region this reports the magnitude of the interaction term at that region's
peak, and — where the store is one whose rows have a known meaning — what the row governs.
"""
from __future__ import annotations

from dataclasses import dataclass

from fontTools.ttLib import TTFont

from .check import _loc, _mixed_difference, _value
from .store import Store, var_stores


@dataclass
class Term:
    table: str
    data_index: int
    row: int
    axes: list[str]
    peak: dict[str, float]
    interaction: float
    marginal_sum: float
    joint_total: float

    @property
    def error_vs_marginals(self) -> float | None:
        """How wrong the marginals are as a prediction of the joint value.

        This is the number that means something: if you moved each axis alone and added
        the results, `marginal_sum` is what you would predict, and `interaction` is how far
        off you would be. Expressed against the prediction, not against the joint value --
        dividing by a joint value that happens to sit near zero produces figures like
        "967%" that are arithmetically true and read as a broken tool.

        None when the marginals predict zero, because a ratio to zero says nothing. The
        absolute magnitude is already in the row.
        """
        if abs(self.marginal_sum) < 1e-9:
            return None
        return self.interaction / abs(self.marginal_sum)

    def line(self) -> str:
        axes = "x".join(self.axes)
        at = ", ".join(f"{a}={self.peak[a]:g}" for a in self.axes)
        err = self.error_vs_marginals
        err_s = "     n/a" if err is None else f"{err:+8.1%}"
        return (f"{self.table:<5} VarData[{self.data_index}] row {self.row:<4} {axes:<14} "
                f"at {at:<22} marginals predict {self.marginal_sum:>10.2f}  actual "
                f"{self.joint_total:>10.2f}  miss {self.interaction:>+9.2f}  {err_s}")


def interaction_terms(path: str, min_magnitude: float = 1e-9) -> list[Term]:
    font = TTFont(path)
    if "fvar" not in font:
        return []
    tags = [a.axisTag for a in font["fvar"].axes]
    terms: list[Term] = []
    for st in var_stores(font):
        for di, data in enumerate(st.store.VarData):
            cols = st.columns(di)
            joint = [(c, r) for c, r in cols
                     if r < len(st.supports) and len(st.supports[r]) > 1]
            for row in range(len(data.Item)):
                for col, ri in joint:
                    if col >= len(data.Item[row]):
                        continue
                    axes = sorted(st.supports[ri])
                    peak = {a: st.supports[ri][a][1] for a in axes}
                    I = _mixed_difference(st, di, row, tags, axes, peak)
                    if abs(I) < min_magnitude:
                        continue
                    joint_total = _value(st, di, row, _loc(tags, **peak))
                    marginal_sum = sum(
                        _value(st, di, row, _loc(tags, **{a: peak[a]})) for a in axes
                    )
                    terms.append(Term(st.table, di, row, axes, peak, I,
                                      marginal_sum, joint_total))
    terms.sort(key=lambda t: abs(t.interaction), reverse=True)
    return terms
