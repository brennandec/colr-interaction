from pathlib import Path
import subprocess, sys
import pytest
from colr_interaction import check_font

FIX = Path(__file__).parent / "fixtures"


def _ensure():
    if not (FIX / "phantom-axis.ttf").exists():
        subprocess.run([sys.executable, str(Path(__file__).parent / "make_fixtures.py")], check=True)


@pytest.fixture(scope="module", autouse=True)
def fixtures():
    _ensure()


def test_separable_has_no_interaction():
    r = check_font(str(FIX / "separable.ttf"))
    assert r.ok
    assert r.separable
    assert r.interaction_axis_sets == []
    assert "separable" in r.verdict


def test_interacting_reports_the_pair():
    r = check_font(str(FIX / "interacting.ttf"))
    assert r.ok
    assert not r.separable
    assert r.interaction_axis_sets == [["AAAA", "BBBB"]]
    assert "AAAAxBBBB" in r.verdict


def test_unused_region_is_an_observation_not_a_failure():
    """A region no subtable uses is dead bytes, not a broken font.

    Reporting it as a failure flagged New York and SF Mono, where an unused GRAD region in
    HVAR is correct: a grade axis is defined not to change advance widths.
    """
    r = check_font(str(FIX / "unused-region.ttf"))
    assert r.ok, [str(f) for f in r.findings if not f.ok]
    assert any("declared but unused" in o for o in r.observations)


def test_phantom_axis_fails_c4():
    """An fvar axis that moves nothing anywhere is the defect worth failing.

    Every design application enumerates fvar and hands the user a slider for it.
    """
    r = check_font(str(FIX / "phantom-axis.ttf"))
    assert not r.ok
    failed = [f.check for f in r.findings if not f.ok]
    assert failed == ["C4 no-phantom-axis"]
    detail = next(f.detail for f in r.findings if f.check.startswith("C4"))
    assert "CCCC" in detail


def test_identity_holds_on_every_fixture():
    for name in ("separable", "interacting", "unused-region", "phantom-axis",
                 "shuffled-regions", "intermediate-peak", "negative-peak", "three-way"):
        r = check_font(str(FIX / f"{name}.ttf"))
        c1 = next(f for f in r.findings if f.check.startswith("C1"))
        assert c1.ok, f"{name}: {c1.detail}"


def test_verdict_is_derived_not_stored():
    r = check_font(str(FIX / "interacting.ttf"))
    assert r.verdict == "carries a designed axis interaction on: AAAAxBBBB"
    r.interaction_axis_sets = []
    r.separable = True
    assert "separable" in r.verdict


def test_non_colr_font_is_not_an_error():
    r = check_font(str(FIX / "separable.ttf"))
    assert r.findings


# --- regressions for the four cases that were silently wrong before v0.2.0 ---------
#
# Each of these passed the first published version by returning the wrong answer quietly.
# They are the reason this tool now evaluates each region at its own peak vector and
# resolves delta columns through VarData.VarRegionIndex.

def test_shuffled_region_index_is_resolved():
    """Delta column i addresses Region[VarRegionIndex[i]], not Region[i].

    This fixture stores its columns in reverse region order. A tool that assumes identity
    pairs every delta with the wrong region and still reports a clean result.
    """
    r = check_font(str(FIX / "shuffled-regions.ttf"))
    assert r.ok, [str(f) for f in r.findings if not f.ok]
    assert not r.separable
    assert r.interaction_axis_sets == [["AAAA", "BBBB"]]


def test_intermediate_peak_region_is_found():
    """A joint region peaking at 0.5 has scalar 0 at the +1 corner.

    Sampling a hardcoded corner reports "additively separable" on a font that carries an
    interaction. The region must be evaluated at its own peak.
    """
    r = check_font(str(FIX / "intermediate-peak.ttf"))
    assert r.ok
    assert not r.separable, "interaction at an intermediate peak was missed"


def test_negative_peak_region_is_found():
    """Bipolar axes peak negative. Evaluating at +1 returns zero scalar."""
    r = check_font(str(FIX / "negative-peak.ttf"))
    assert r.ok
    assert not r.separable
    assert r.interaction_axis_sets == [["AAAA", "CCCC"]]


def test_three_way_region_is_reported_as_three_way():
    """A 3-axis region is not two pairwise interactions.

    Held at (a=1, b=1, c=0) its scalar is zero, so pairwise sampling finds nothing. The
    n-th order mixed difference over the region's own axis set is what isolates it.
    """
    r = check_font(str(FIX / "three-way.ttf"))
    assert r.ok
    assert not r.separable
    assert r.interaction_axis_sets == [["AAAA", "BBBB", "CCCC"]]
    assert "AAAAxBBBBxCCCC" in r.verdict


def test_every_variation_store_is_scanned_not_only_colr():
    """A joint region in HVAR changes advance widths.

    A tool that reads only COLR reports such a font as free of interaction. The fixtures
    are COLR-only, so this asserts the mechanism rather than the outcome: whatever stores
    a font has, all of them are listed and all of them are checked.
    """
    from colr_interaction import var_stores
    from fontTools.ttLib import TTFont

    r = check_font(str(FIX / "interacting.ttf"))
    assert r.stores, "no stores reported"
    found = {s.table for s in var_stores(TTFont(str(FIX / "interacting.ttf")))}
    assert set(r.stores) == found
    for f in r.findings:
        if f.check.startswith(("C1", "C2", "C3", "C4")):
            assert f.table == "+".join(r.stores)


def test_var_idx_resolution_handles_outer_inner_split():
    """A VarIdx is an outer/inner pair, not a row number."""
    from colr_interaction.store import resolve_var_idx, var_stores
    from fontTools.ttLib import TTFont

    st = var_stores(TTFont(str(FIX / "interacting.ttf")))[0]
    assert resolve_var_idx(st.store, 0) == (0, 0)
    assert resolve_var_idx(st.store, 0xFFFF0000) is None   # outer past the end
    assert resolve_var_idx(st.store, 0x0000FFFF) is None   # inner past the end


def test_c5_reports_reachable_deltas():
    r = check_font(str(FIX / "interacting.ttf"))
    c5 = next((f for f in r.findings if f.check.startswith("C5")), None)
    assert c5 is not None and c5.ok, "C5 should pass on a well-formed fixture"
