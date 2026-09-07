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
