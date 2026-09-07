from pathlib import Path
import subprocess, sys
import pytest
from colr_interaction import check_font

FIX = Path(__file__).parent / "fixtures"


def _ensure():
    if not (FIX / "separable.ttf").exists():
        subprocess.run([sys.executable, str(Path(__file__).parent / "make_fixtures.py")], check=True)


@pytest.fixture(scope="module", autouse=True)
def fixtures():
    _ensure()


def test_separable_has_no_interaction():
    r = check_font(str(FIX / "separable.ttf"))
    assert r.ok
    assert r.separable
    assert r.interaction_axis_pairs == []
    assert "separable" in r.verdict


def test_interacting_reports_the_pair():
    r = check_font(str(FIX / "interacting.ttf"))
    assert r.ok
    assert not r.separable
    assert r.interaction_axis_pairs == [["AAAA", "BBBB"]]
    assert "AAAAxBBBB" in r.verdict


def test_phantom_region_fails_c4():
    r = check_font(str(FIX / "phantom.ttf"))
    assert not r.ok
    failed = [f.check for f in r.findings if not f.ok]
    assert failed == ["C4 no-phantom-axis"]


def test_identity_holds_on_every_fixture():
    for name in ("separable", "interacting", "phantom"):
        r = check_font(str(FIX / f"{name}.ttf"))
        c1 = next(f for f in r.findings if f.check.startswith("C1"))
        assert c1.ok, f"{name}: {c1.detail}"


def test_verdict_is_derived_not_stored():
    r = check_font(str(FIX / "interacting.ttf"))
    assert r.verdict == "carries a designed axis interaction on: AAAAxBBBB"
    r.interaction_axis_pairs = []
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
    assert r.interaction_axis_pairs == [["AAAA", "BBBB"]]


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
    assert r.interaction_axis_pairs == [["AAAA", "CCCC"]]


def test_three_way_region_is_reported_as_three_way():
    """A 3-axis region is not two pairwise interactions.

    Held at (a=1, b=1, c=0) its scalar is zero, so pairwise sampling finds nothing. The
    n-th order mixed difference over the region's own axis set is what isolates it.
    """
    r = check_font(str(FIX / "three-way.ttf"))
    assert r.ok
    assert not r.separable
    assert r.interaction_axis_pairs == [["AAAA", "BBBB", "CCCC"]]
    assert "AAAAxBBBBxCCCC" in r.verdict
