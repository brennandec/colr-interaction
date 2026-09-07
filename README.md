# colr-interaction

Conformance checks for **axis interaction** in OpenType COLR v1 variable fonts.

A variation region may peak on more than one axis. A delta stored against such a region
contributes only when all of those axes are engaged together — so it is absent from every
single-axis view of the font and appears only in the interior of the designspace.

This tool reports whether a given binary actually implements that, so a claim about a font
can be checked against the font instead of taken on trust.

Run it on the fixtures in this repo and you get exactly this:

```
$ python -m colr_interaction tests/fixtures/interacting.ttf tests/fixtures/phantom.ttf
tests/fixtures/interacting.ttf
  axes ['AAAA', 'BBBB']  regions 3
  interaction regions on: AAAAxBBBB
  PASS  C1 interaction-identity  holds on all rows; interaction present
  PASS  C2 marginal-blindness  joint deltas absent from every single-axis view
  PASS  C3 zero-corner  every variable attribute resolves to its static value at the default
  PASS  C4 no-phantom-axis  every declared region carries at least one nonzero delta
  -> carries a designed axis interaction on: AAAAxBBBB

tests/fixtures/phantom.ttf
  axes ['AAAA', 'BBBB']  regions 2
  PASS  C1 interaction-identity  holds on all rows; interaction identically zero
  PASS  C2 marginal-blindness  joint deltas absent from every single-axis view
  PASS  C3 zero-corner  every variable attribute resolves to its static value at the default
  FAIL  C4 no-phantom-axis  region 1 (BBBB) declared but no row uses it
  -> does not conform
```

The last line is generated from the bytes. Nothing in this tool lets you write it by hand.

## The measurement

For a variable attribute evaluated over two axes, the interaction is the second-order
mixed difference:

```
I(a, b) = v(a, b) - v(a, 0) - v(0, b) + v(0, 0)
```

`I ≡ 0` means the attribute is **additively separable**: the axes are independent and the
joint behaviour is fully predicted by the two marginals. `I ≠ 0` means the joint behaviour
is not predicted by either marginal — there is something in the font that you cannot see by
moving one slider at a time.

Both are legitimate designs. This tool has no opinion about which you should ship. It
reports which one you did.

## Why this might be worth running

Multi-axis regions have been legal since variable fonts shipped, and compilers emit them
routinely — an `opsz × wght` region is ordinary. What is not routine is checking them.

How thin the checking is, measured rather than asserted: at the time of writing, a code
search of [fontbakery](https://github.com/googlefonts/fontbakery) — the QA suite most font
projects run, and the one every Google Fonts submission passes through — returns **zero**
occurrences of `VarRegionList` and **zero** of `PeakCoord`. It does not inspect the
variation region model at all. fontTools implements the model (53 occurrences of
`PeakCoord`) but implementing a model is not checking conformance to it.

That is evidence, not proof: GitHub code search is not exhaustive and I have not audited
every private toolchain in the industry. **If you know of a tool that already does this,
open an issue and I will link it here.** The claim is meant to be falsifiable, and it would
be more useful to me to be wrong early than to be wrong in public for a year.

- A font can declare an axis whose every delta row is zero. Every design application will
  still enumerate `fvar` and draw the user a slider for a dimension that moves nothing.
  That is not an internal inconsistency; it is **a defect with a user interface**. `C4`
  catches it.
- A font can be described as having a designed interaction between two axes and ship
  separable deltas. `C1` settles it in one run.
- A font can claim its default instance is identical to a static build. `C3` checks it.

We found three phantom-axis fonts in our own tree with this, including two already shipped,
and one font whose entire variation store was zeros. The check is cheap and it finds things.

## Checks

| | | |
|---|---|---|
| `C1` | interaction-identity | For every joint-support region, the mixed difference evaluated from the store must equal that region's own contribution, exactly. Evaluated **at each region's own peak vector** — not a hardcoded corner — so intermediate regions, negative peaks and 3+ axis regions are all handled. For an *n*-axis region it is the *n*-th order mixed difference, which is what isolates a genuinely *n*-way term from the pairwise ones. |
| `C2` | marginal-blindness | A joint delta must contribute nothing to any single-axis evaluation — absent from the marginals, not merely small in them. |
| `C3` | zero-corner | At the designspace default every region scalar is zero, so every variable attribute must resolve to its static value. |
| `C4` | no-phantom-axis | Fails a region no delta row uses, and a `VarData` whose every row is zero. |
| `C5` | base-immutability | Opt-in (`--check-base`). The topmost layer of each glyph's `PaintColrLayers` must contain no variable paint. Where a font puts an interaction on *translation*, this is what keeps the read shape from moving under any axis combination. |

`C1`–`C4` run on any COLR v1 font with a variation store. `C5` assumes the common
"decorative layers under a static base" construction and is off by default.

## Install

```
pip install colr-interaction        # once published
pip install -e .                    # from a clone
```

Requires `fonttools >= 4.40`.

## Use

```
python -m colr_interaction FONT [FONT ...]
    --json                  machine-readable report
    --check-base            also run C5
    --require-interaction   exit non-zero if the font is additively separable
```

Exit codes: `0` conforms · `1` a check failed (or `--require-interaction` on a separable
font) · `2` a font could not be read.

`--require-interaction` is for CI on a build that claims a designed interaction. Without
it the tool still verifies the identity and reports which case the binary is, rather than
failing a font that never claimed anything.

As a library:

```python
from colr_interaction import check_font
report = check_font("MyFont.ttf", check_base=True)
print(report.verdict, report.ok, report.interaction_axis_pairs)
```

## Fixtures

`tests/fixtures/` is built from scratch by `tests/make_fixtures.py` — no third-party font
data is vendored. Three fonts: `separable` (two single-axis regions), `interacting` (adds a
joint region with a delta), `phantom` (declares a region no row uses, so `C4` fails).

## Scope, and what this is not

This checks the **variation store**, which is the part a renderer must agree on. It does not
rasterize and it makes no claim about rendered pixels: rendered output is renderer-dependent
(FreeType, CoreText and DirectWrite legitimately differ on subpixel antialiasing and
floating-point rounding), so a rendered-output hash is a claim about a pinned environment,
not a property of a font. Anything asserting otherwise is overclaiming.

It also is not a general font validator. It answers one question that existing validators do
not ask.

## Correctness notes

Three classes of bug were found in this tool's own first published version, all by people
and fonts outside the house that wrote it. They are listed here because the fixtures that
now cover them are the most useful part of the repo:

- **Delta column ≠ region index.** Column *i* of a `VarData` row addresses
  `Region[VarData.VarRegionIndex[i]]`, not `Region[i]`. An optimized font stores only the
  regions a subtable uses. Both fonts this was first written against happened to have
  identity maps, which is exactly why it survived to publication.
  Fixture: `shuffled-regions.ttf`.
- **Sampling a hardcoded corner.** A joint region peaking at 0.5, or peaking negative on a
  bipolar axis, has scalar zero at +1 — so a corner sample reports "separable" on a font
  that plainly interacts. Every region is now evaluated at its own peak vector.
  Fixtures: `intermediate-peak.ttf`, `negative-peak.ttf`.
- **Pairwise sampling misses n-way regions.** A three-axis region held at *(1, 1, 0)* has
  scalar zero. Fixture: `three-way.ttf`.

An earlier one, kept because the lesson generalises: an unweighted sum of regions matching
an axis pair gives the wrong expected value for an axis whose range is split across
adjacent regions. Each region's contribution must be scalar-weighted.

## Contributing

Bug reports with a font that reproduces are the most useful thing, and the four fixtures
above all came from someone saying "what about…". If a check is wrong, that is worth more
to this repo than a feature.

## License

MIT.
