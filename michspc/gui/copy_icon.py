"""The copy glyph: two rounded rectangles, drawn rather than shipped.

Windows 11 spells "copy" as a pair of offset rounded rectangles — one sheet
behind another — and that is the symbol a surveyor already knows from File
Explorer and every other application on the machine. The owner asked for that
symbol in place of the word ``Copy`` (docs/DESIGN.md amendment #27).

**Drawn with QPainter, not loaded from a file.** The alternatives were each
worse for a program whose release is eight gates deep:

* a ``.svg`` or ``.png`` asset would put a new file in the build's path — the
  PyInstaller spec, the frozen-bundle self-test and the checksum gate all
  enumerate what ships, and a missing icon inside a bundle is discovered by the
  surveyor rather than by the gate;
* ``QStyle.StandardPixmap`` has no copy glyph on Windows, so it would resolve to
  whatever the platform style happened to offer, or to nothing;
* ``QtSvg`` is a Qt module the bundle does not currently carry.

Nothing here is load-bearing for a coordinate. This module draws a picture; if
it drew the wrong picture the failure is visible and cosmetic. It is kept out of
``result_panel`` so the panel stays a module about showing values, and so the
glyph can be looked at by a test on its own.

The colour is passed in by the caller — the panel reads it from its own palette
— so the glyph follows a light or dark Windows theme rather than pinning black
onto a dark background.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

CANVAS = 16.0
"""The side of the square the geometry below is expressed in. Every dimension
is a fraction of this, so the glyph is resolution-independent: it is drawn at
whatever pixel size is asked for, not scaled up from a 16 px bitmap."""

SHEET_WIDTH = 9.5
SHEET_HEIGHT = 10.0
OFFSET = 3.0
"""One sheet, and how far the back one sits up and to the right of the front.

Read off the Windows 11 shape: two same-sized sheets, the back one visible as an
L along the top and right of the front one. Both sit inside the canvas with a
margin, so the glyph does not touch the button's edge at any size.
"""

FRONT = QRectF(1.5, 4.5, SHEET_WIDTH, SHEET_HEIGHT)
BACK = FRONT.translated(OFFSET, -OFFSET)

CORNER_RADIUS = 1.75
STROKE_WIDTH = 1.25
"""Outlined, not filled — the Fluent "line" weight rather than a solid blob.
A filled glyph at 16 px reads as a smudge, which is the same failure the app
icon's lettering had (amendment #24)."""

SEPARATION = 0.9
"""How much clear space is punched around the front sheet before it is drawn.

Without it the back sheet's outline runs straight through the front one and the
two rectangles read as a single scribble. With it, the front sheet sits in front
of the back sheet the way the Windows glyph does.
"""

_CACHE: dict[tuple[int, str, float], QIcon] = {}
"""Built glyphs, keyed by the three things that change one: the pixel size, the
colour, and the device pixel ratio. The results panel is rebuilt wholesale on
every conversion and every row asks for the same icon, so without this the same
picture would be painted a dozen times per keystroke."""


def copy_pixmap(size: int, color: QColor, device_pixel_ratio: float = 1.0) -> QPixmap:
    """The glyph, painted at ``size`` logical pixels square, on transparency.

    ``device_pixel_ratio`` is the screen's, so the pixmap carries real pixels on
    a 150% or 200% display instead of being scaled up and blurred — the default
    scaling on most current Windows laptops.
    """
    physical = max(1, round(size * device_pixel_ratio))
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.GlobalColor.transparent)

    # The device pixel ratio is stamped on the pixmap AFTER painting, at the
    # bottom - and the order is load-bearing, not style. A QPainter opened on
    # a pixmap that already carries a ratio works in logical coordinates: it
    # arrives pre-scaled by that ratio, and the canvas scale below then
    # compounds with it. At a 125% Windows display that mapped the 16-unit
    # canvas onto 17.5 device pixels of a 14-pixel pixmap, so every button on
    # the results panel showed a glyph with its bottom and right cut off - at
    # 150% a third of it, at 200% half - while 100% displays and the offscreen
    # test platform (both ratio 1.0) rendered it perfectly, which is why no
    # test saw it and the owner did (DESIGN.md amendment #39).
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(physical / CANVAS, physical / CANVAS)

        pen = QPen(color)
        pen.setWidthF(STROKE_WIDTH)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        # The back sheet first, whole.
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(BACK, CORNER_RADIUS, CORNER_RADIUS)

        # Then erase where the front sheet is about to go, so the back sheet's
        # outline stops at the front sheet's edge rather than crossing it.
        clearance = FRONT.adjusted(-SEPARATION, -SEPARATION, SEPARATION, SEPARATION)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.black)  # any opaque colour; it only clears
        painter.drawRoundedRect(
            clearance, CORNER_RADIUS + SEPARATION, CORNER_RADIUS + SEPARATION
        )

        # And the front sheet on top of the hole.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(FRONT, CORNER_RADIUS, CORNER_RADIUS)
    finally:
        # Ends the paint session even if drawing raised. A QPainter still
        # active when its QPixmap is collected warns on stderr and, on some
        # platforms, leaves the pixmap unfinished.
        painter.end()

    pixmap.setDevicePixelRatio(device_pixel_ratio)
    return pixmap


def copy_icon(size: int, color: QColor, device_pixel_ratio: float = 1.0) -> QIcon:
    """A ``QIcon`` carrying the glyph. Cached; callers must not modify it."""
    key = (int(size), color.name(QColor.NameFormat.HexArgb), float(device_pixel_ratio))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    icon = QIcon(copy_pixmap(size, color, device_pixel_ratio))
    _CACHE[key] = icon
    return icon
