# Michigan SPC Zone Converter

Converts survey coordinate files between the three Michigan State Plane
Coordinate System of 1983 zones — North (2111), Central (2112) and South
(2113) — and between State Plane and geodetic positions.

All three Michigan zones are Lambert conformal conic. The projection
mathematics come from **NOAA Manual NOS NGS 5, *State Plane Coordinate System
of 1983*** (Stem, 1989; reprinted with minor corrections 1990), which is
committed to this repository at `docs/NOAA_Manual_NOS_NGS_0005.pdf`. No
third-party geodesy library is used at runtime — every constant and equation
is traceable to a cited page of that manual.

Michigan SPCS 83 is legislated in **International feet** (manual Table 1.5,
p. 9), and that is the tool's default unit. US survey feet and meters are
selectable.

## Running from source

```bash
run.bat
```

Requires Python 3.14 and PySide6. See `docs/DESIGN.md` for the design
authority and `CLAUDE.md` for the working summary.

## Tests

```bash
py -m pytest
```

The suite must also pass under `-O`, which strips assertions:

```bash
py -O -m pytest
```

## Status

Under development. Not yet released.
