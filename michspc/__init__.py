"""Michigan SPC Zone Converter.

Converts survey coordinate files between the three Michigan State Plane
Coordinate System of 1983 zones, and between State Plane and geodetic
positions.

Primary reference: NOAA Manual NOS NGS 5, "State Plane Coordinate System of
1983" (Stem 1989, reprinted with minor corrections March 1990), committed at
``docs/NOAA_Manual_NOS_NGS_0005.pdf``. Page citations throughout this package
refer to that PDF's own page numbering.
"""

# The single source of truth for the application version. The manual, the
# build script, and the Inno installer all read this literal; nothing else
# declares a version. The "-dev" marker is refused by the release gate, so the
# shipped number space stays unambiguous (METHOD.md section 6).
__version__ = "0.6.0"

APP_NAME = "MCX"

APP_FULL_NAME = "Martin Coordinate Exchange"
"""What MCX stands for. Written out wherever there is room for it - the job
record's header, the installer, the about text - because three letters alone do
not tell a reader six months later what produced the file."""

APP_PUBLISHER = "DMARTIN"
"""The publisher Windows shows in Installed apps and in the file properties."""
