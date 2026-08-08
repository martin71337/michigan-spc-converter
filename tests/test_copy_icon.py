"""The copy glyph: is it actually two rounded rectangles, and is it visible?

Nothing here is load-bearing for a coordinate — this module draws a picture.
What it is worth pinning is that the picture is *there*: a glyph that silently
paints nothing leaves a row of blank flat buttons beside the numbers, and the
control a surveyor uses to move a coordinate to the clipboard would be
invisible with no error anywhere. The old caption said "Copy" in words and
could not fail this way; the glyph can, so it is checked.

The shape checks below read individual pixels at hand-derived positions rather
than comparing against a stored reference image. A reference image would fail on
any harmless change to the geometry and tell whoever ran it nothing about what
broke.
"""

from __future__ import annotations

import os

# MUST precede any Qt import (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402

from michspc.gui import copy_icon as glyph  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402

BLACK = QColor("black")

SIZE = 64
"""Everything below is measured on a 64 px rendering: four device pixels per
canvas unit, so a hand-derived canvas coordinate lands on a pixel rather than
between two."""

SCALE = SIZE / glyph.CANVAS


@pytest.fixture(scope="module")
def qapp():
    """A QPixmap needs a QGuiApplication before it can be constructed."""
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


def at(image, x_canvas: float, y_canvas: float) -> int:
    """The alpha at a canvas coordinate, 0-255."""
    return image.pixelColor(round(x_canvas * SCALE), round(y_canvas * SCALE)).alpha()


@pytest.fixture
def image(qapp):
    return glyph.copy_pixmap(SIZE, BLACK).toImage()


def painted_fraction(image) -> float:
    total = image.width() * image.height()
    painted = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    return painted / total


def test_the_glyph_paints_something(image):
    """The failure this file exists for: an invisible copy button."""
    assert painted_fraction(image) > 0.05


def test_an_unpainted_pixmap_would_fail_that_check(qapp):
    """Anti-vacuousness. The check above must be able to see an empty glyph."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap

    blank = QPixmap(SIZE, SIZE)
    blank.fill(Qt.GlobalColor.transparent)

    assert painted_fraction(blank.toImage()) == 0.0


def test_it_is_two_sheets_one_behind_the_other(image):
    """The Windows 11 shape, checked where it differs from anything else.

    Two same-sized rounded rectangles, the back one offset up and to the right,
    both outlined rather than filled. Six hand-derived probes:

      * the front sheet's left edge and the back sheet's right edge are drawn,
        which is what makes it two sheets rather than one;
      * both sheets' interiors are clear, which is what makes them outlines
        rather than blobs — a filled glyph reads as a smudge at 16 px;
      * the back sheet's top edge is drawn where the front sheet does not
        reach it, and its left edge is NOT drawn where the front sheet covers
        it, which is what makes one sheet sit in front of the other rather
        than the two crossing like a hash.
    """
    front, back = glyph.FRONT, glyph.BACK

    # Drawn: the two outer edges that give the glyph its silhouette.
    assert at(image, front.left(), front.center().y()) > 200
    assert at(image, back.right(), back.top() + 2.0) > 200

    # Clear: both interiors.
    assert at(image, front.center().x(), front.center().y()) == 0
    assert at(image, back.center().x() + 2.0, back.top() + 2.5) == 0

    # The back sheet's top edge shows above the front sheet.
    assert at(image, back.center().x(), back.top()) > 200
    # Its left edge does not, because the front sheet is in front of it.
    assert at(image, back.left(), back.bottom() - 1.0) == 0


def test_the_glyph_is_drawn_in_the_colour_it_was_asked_for(qapp):
    """It follows the palette, so a dark Windows theme does not get black on
    near-black. The panel passes its own ``WindowText``."""
    red = glyph.copy_pixmap(SIZE, QColor("red")).toImage()
    front = glyph.FRONT

    drawn = red.pixelColor(
        round(front.left() * SCALE), round(front.center().y() * SCALE)
    )
    assert drawn.alpha() > 200
    assert drawn.red() > 200
    assert drawn.green() < 60
    assert drawn.blue() < 60


def test_a_high_dpi_screen_gets_real_pixels_not_a_scaled_up_one(qapp):
    """Windows laptops default to 150% or 200%. A 14 px pixmap stretched to 28
    is a blurred glyph; this asks for 28 real pixels and says it is worth 14.

    Dimensions only. That this pixmap's CONTENT is right is the next test's
    job, and for three releases it was nobody's: this one passed while every
    scaled display showed a glyph with its bottom and right cut off.
    """
    pixmap = glyph.copy_pixmap(14, BLACK, device_pixel_ratio=2.0)

    assert pixmap.width() == 28
    assert pixmap.height() == 28
    assert pixmap.devicePixelRatio() == 2.0


@pytest.mark.parametrize("device_pixel_ratio", [1.25, 1.5, 2.0])
@pytest.mark.parametrize("size", [11, 14])
def test_a_scaled_display_gets_the_same_picture_a_100_percent_one_does(
    qapp, size, device_pixel_ratio
):
    """The whole glyph, at every Windows display scale — byte-identical.

    A pixmap asked for at ``size`` logical pixels under a device pixel ratio
    carries ``round(size * ratio)`` physical pixels, and its content must be
    EXACTLY the content a 100% display gets when it asks for that many pixels
    outright: same canvas, same scale, same bytes. That identity is what the
    fix restores, so it is what is pinned — no probe positions to drift, no
    antialiasing tolerance to go stale (the #31 class).

    What it catches, because it caught it: ``copy_pixmap`` stamped the device
    pixel ratio on the pixmap BEFORE opening the painter, so the painter
    arrived pre-scaled by the ratio and the canvas scale compounded with it —
    the 16-unit canvas mapped onto 17.5 device pixels of a 14-pixel pixmap at
    125%, and every copy button on the results panel lost the bottom and right
    of its glyph. At 100%, and on this offscreen test platform, both scales
    are 1.0 and nothing showed; the owner's 125% display is where it was
    found (DESIGN.md amendment #39). Falsified by seeding that order back:
    all six parametrizations fail.

    ``11`` is COPY_ICON_SIZE, the size the panel actually asks for; ``1.25``
    is the display it was found on. The ratios cover the scales Windows
    actually offers.
    """
    physical = round(size * device_pixel_ratio)

    reference = glyph.copy_pixmap(physical, BLACK).toImage()
    scaled = glyph.copy_pixmap(size, BLACK, device_pixel_ratio).toImage()

    # The ratio itself is not under test here (the test above pins it), and
    # QImage equality compares it; neutralize it so the comparison is the
    # pixels and nothing else.
    scaled.setDevicePixelRatio(1.0)
    reference.setDevicePixelRatio(1.0)

    assert scaled == reference


def test_the_same_request_returns_the_same_icon(qapp):
    """The panel is rebuilt wholesale on every keystroke that invalidates a
    result, and every row asks for the same glyph."""
    first = glyph.copy_icon(14, BLACK)
    again = glyph.copy_icon(14, BLACK)

    assert first is again
    assert first.isNull() is False

    # A different colour is a different glyph, not a cache hit.
    assert glyph.copy_icon(14, QColor("red")) is not first
