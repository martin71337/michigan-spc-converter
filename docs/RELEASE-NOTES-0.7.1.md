# MCX 0.7.1

**A finished, verified tool.** MCX moves survey coordinates between Michigan's
three State Plane zones and the 19 SPCS2022 zones, between State Plane and
geodetic positions on either reference frame, converts elevations between
vertical datums and between geoid models, accepts GNSS ellipsoid heights, and
documents every job well enough to defend it. It is in production use by a
licensed professional surveyor.

This is an interface release. **No calculation changed, and no coordinate,
elevation or factor this program produces differs from 0.7.0 by any amount.**

## Drag a file onto the Multi point tab

A coordinate file dragged from Explorer and dropped anywhere on the Multi
point tab lands in the Input file box, exactly as if Browse had chosen it.
Convert arms the same way, and the path is written the way the file dialog
writes it.

The drop is accepted for exactly one thing: a single file that exists on this
machine. Anything else is refused at the border, with the no-drop cursor,
before it can land anywhere:

- **two or more files** — the program will not pick one for you;
- **a folder** — folders have their own button;
- **a path that does not exist**, or **a web address**.

Dropping onto the Input file or Output folder boxes themselves does nothing:
those boxes take a typed path or a chosen one, never a dropped one, so a drop
cannot write a stray string into either.

Nothing else on screen changed, and nothing about the way a job is converted
or recorded changed. The Single point tab is untouched.

## The audit CSV states the geodetic position in DMS

`<stem>_full.csv` carries two new columns, **Latitude (DMS)** and
**Longitude (DMS)**, directly after `Longitude (neg west)`: the same
geodetic position the two decimal columns before them hold, as degrees,
minutes and seconds to five places with a hemisphere letter —
`42-43-57.00000 N`, `84-33-19.80000 W`. The digits are the ones the Single
point tab shows for the same point; only the punctuation differs, because a
degree symbol in a CSV does not survive Excel.

**If a spreadsheet of yours reads this file by column position, note that
every column after `Longitude (neg west)` has moved two places to the
right.** Readers that go by the heading are unaffected.

## Converting to geodetic writes the positions twice: decimal and DMS

A job whose target is geodetic now writes **four** files into its archive
instead of three. The clean export is named `<job>_GEODETIC_DD.csv` — the
same file as before, byte for byte, under a name that says what it holds —
and beside it `<job>_GEODETIC_DMS.csv` carries the same rows with the
latitude and longitude in degrees, minutes and seconds:

    101,42-43-57.00000 N,84-33-19.80000 W,900.000,IRON PIPE

The point, elevation and description columns are identical between the two
files. The DMS file has no sign convention to state — the letter says which
hemisphere — so it reads the same whichever way the job wrote its
longitudes. It is for reading and transcription: **not for CAD import**, and
this program will not read it back as an input file. Convert from the `_DD`
file. Every other direction's archive is unchanged, name and contents.

**If anything of yours opens `<job>_GEODETIC.csv` by name, it is now
`<job>_GEODETIC_DD.csv`.** The archive's own name is unchanged.

Everywhere a DMS angle is written to a file, the fields are separated by a
dash: the two audit columns above, this export, and **the convergence
angle** in the audit CSV's two convergence columns and the job record —
`-16-49-17.76` where earlier releases wrote `-16 49 17.76`. Same sign,
same digits. **If anything of yours parses the convergence columns by
splitting on spaces, it now needs to split on dashes after the sign.**

## Built against NGS's beta products

As in 0.7.0: NGS's SPCS2022 zone definitions and its NCAT v3 service are
pre-release, and this release is built against them deliberately, at the
owner's instruction. Every beta-derived number carries its capture date and
the SHA-256 of the NGS file it came from (`docs/REFREEZE-NSRS.md`), and the
release build refuses to run unless that is acknowledged on the command line.

## Verified

- **3,802 automated tests**, green in both run modes, including the
  cross-version pin that digests what nine ordinary jobs write against what
  an earlier release produced — so a release that quietly moved a number
  would fail a test. It did not: the clean exports are byte-identical (the
  geodetic one under its new `_DD` name), and the audit CSV is
  byte-identical once its two new columns are set aside and its convergence
  cells are read under their old spacing.
- **The DMS export is read back before it is written**, through the same
  parser the Single point tab uses for typed DMS, and every cell is compared
  against the decimal file it duplicates. A DMS file that could disagree
  with its decimal sibling is refused, and nothing is written.
- **The DMS cells are checked against NGS NCAT's own positions** at every
  frozen anchor in both geodetic directions, by an independent reading
  written in the test, to half of the cell's last place.
- **Ten tests guard the drop itself.** Every one drives a real drag-enter and
  drop through Qt's own event dispatch, so what is pinned is what the tab does
  when Explorer hands it a file: the one-file rule, each refusal, the box
  filled, Convert armed, and a written result kept. Eight defects were seeded
  against them and every one was caught.
- **Nine build gates**, including a **self-test run inside the frozen
  application** against NGS's own figures.

Verify the download against `SHA256SUMS.txt` on this page.
