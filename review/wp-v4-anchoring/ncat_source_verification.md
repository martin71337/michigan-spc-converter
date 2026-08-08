# NGS source verification, read first-hand 2026-08-07

Everything below was fetched and read directly, not summarised by a tool.

## INTG (the geoid interpolator)

`https://www.ngs.noaa.gov/GEOID/G99BM/intg.f`

    irown = nint((xlat-glamn(k)) / dla(k)) + 1
    icoln = nint((xlon-glomn(k)) / dlo(k)) + 1

then reads rows `irown-1, irown, irown+1` and columns `icoln-1, icoln, icoln+1`.

`nint` is Fortran's NEAREST integer. So INTG anchors its 3x3 on the nearest
node - the centred stencil. This program's `interpolate_biquadratic` anchors at
`int(row) - 1`, which is NOT that.

Corroborated by NOAA Technical Memorandum NOS NGS-84, *Biquadratic
Interpolation*, which describes the method as relying on "the nearest 3x3 set of
grid points to the point of interpolation".

**Consequence:** DESIGN.md #8's "NGS does not document which interpolation
scheme its INTG program uses" is false, and the claim that this program's
anchoring is INTG's is false. Both corrected.

## NCAT's VERTCON reader

`https://raw.githubusercontent.com/noaa-ngs/ncat-lib/main/src/gov/noaa/ngs/grid/Vertcon.java`

    int row = getGridRow(lat);
    int col = getGridColumn(lon);
    intpPoint[0] = (lon - minlon - dlon * (col - 1)) / dlon;
    intpPoint[1] = (lat - minlat - dlat * (row - 1)) / dlat;
    return getCells(gridfh, row - 1, col - 1, numRows, numCols);

The block starts one node below `row`, so it is CENTRED on `row`, and the
interpolation coordinate is measured from that centre node. Same convention as
INTG.

    switch (gridRank) {
        case 3: intpVal = intp.biquadratic(); break;
        case 2: ... 2x2 bilinear ...

**Both grids go through the same code path** - `Vertcon.java` handles `.trn` and
`.err` alike, distinguished only by a `gridType` string ("err ot trn", their
typo). That is independent confirmation that plan section 2.5's "the error grid
is bilinear" was never an NGS property.

**The bilinear fallback is for MISSING DATA ONLY.** From `GridManager.java`:

    public int rankBlock(double[] block) {
        boolean missing = false;
        for (double d : block) {
            if ((int) d == MISSING_DATA_INDICATOR) { missing = true; break; }
        }

Our grids contain no missing-data cells (scanned: no non-finite, no -88.8888, no
+/-9999, no 999.0), so in Michigan NCAT always takes the biquadratic branch.
This closes the worry that NCAT might be silently bilinear somewhere.

`Interpolator.biquadratic()` is structurally identical to ours:

    fx0 = quad(x, g[0], g[1], g[2])
    fx1 = quad(x, g[3], g[4], g[5])
    fx2 = quad(x, g[6], g[7], g[8])
    fx  = quad(y, fx0, fx1, fx2)

Quadratic along each of three rows, then along the column. Same as
`interpolate_biquadratic_nearest_node`.

## What is NOT resolved by the source

**Nothing in `Vertcon.java` clamps, floors or `abs()`es a negative error-grid
result.** So NCAT's published source does not explain why NCAT returns +0.011 m
at 42.475 N / 83.125 W where a faithful nearest-node biquadratic gives
-0.00965 m. Either the deployed service differs from this source, or the value
is post-processed above this layer, or `getGridRow` differs from what is assumed
here (its body is in a subclass not present at the paths tried).

That is the open question, and it is exactly the one the Codex gate identified:
**NCAT's downstream treatment of a negative biquadratic error result** - not the
stencil selection, which is now confirmed three ways.
