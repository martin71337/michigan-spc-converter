"""Generate the Windows multi-resolution ``.ico`` from the master artwork.

**A build step, not a committed artefact.** The owner's artwork lives once, at
``assets/icon/mcx-1024.png`` (1024x1024, 8-bit RGBA). Committing a
hand-made ``.ico`` beside it would create a second representation of the same
fact, and the two would eventually disagree about what the program looks like
(docs/DESIGN.md amendment #15 note 1, docs/method/METHOD.md section 5). So the
``.ico`` is derived here, into build output, every time it is needed.

**Standard library only — no Pillow.** Everything needed is in ``zlib`` and
``struct``: the master is a non-interlaced 8-bit RGBA PNG, which is the one
colour type this decoder accepts and refuses anything else; the resampler is a
separable area average, which is the correct filter for downscaling; and the
``.ico`` container is a handful of little-endian structures. Keeping the build
hermetic is worth the two hundred lines, and it means the icon can be rebuilt on
a machine with nothing installed but Python.

Two details that are easy to get wrong and are done deliberately here:

*Alpha is premultiplied before averaging and divided out afterwards.* The
artwork has a transparent background. Averaging raw RGB across the boundary
between an opaque pixel and a transparent one blends in whatever colour happens
to sit in the transparent pixel's unused RGB slots, which shows up as a dark or
white fringe around the compass at 16 and 32 px. Weighting each pixel's colour
by its own alpha is what makes the edge come out clean.

*Every size is written as a 32-bit BGRA DIB, including 256.* PNG-compressed
entries are legal in an ``.ico`` from Windows Vista onward and would make the
file smaller, but the classic DIB form is what every consumer reads without
argument, and this file is read by Explorer, the Qt window, PyInstaller and Inno
Setup. Size is not a constraint here.

Run it directly::

    py tools/make_icon.py                 # -> build/icon/mcx.ico
    py tools/make_icon.py --output X.ico
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from array import array
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MASTER_PNG = REPO_ROOT / "assets" / "icon" / "mcx-1024.png"
"""The owner's artwork. The single authoritative representation of the icon."""

DEFAULT_OUTPUT = REPO_ROOT / "build" / "icon" / "mcx.ico"
"""Build output, git-ignored. ``michspc.gui.icon`` looks here; the two are
pinned to each other by ``tests/test_icon.py`` so they cannot drift apart."""

ICON_SIZES = (16, 32, 48, 64, 128, 256)
"""The six sizes Windows asks for (docs/DESIGN.md amendment #15 note 1).

16 and 32 are the taskbar and small-icon views, 48 is the Explorer "medium
icons" view, 256 is the largest Windows requests. All square.
"""

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\x0a"

_RGBA = 6
"""PNG colour type 6: truecolour with alpha, 4 channels."""

_CHANNELS = 4


class IconError(Exception):
    """The master artwork is not what this tool knows how to read."""


# ---------------------------------------------------------------------------
# PNG decoding
# ---------------------------------------------------------------------------


def decode_png_rgba8(data: bytes) -> tuple[int, int, bytearray]:
    """Decode a non-interlaced 8-bit RGBA PNG to a flat RGBA byte buffer.

    Returns ``(width, height, pixels)`` where ``pixels`` is
    ``width * height * 4`` bytes, row-major, top row first.

    Every constraint is checked and refused by name rather than assumed. This
    reads one specific file that is committed alongside it, so an unhandled
    variant means the artwork was replaced with something else, and silently
    producing a garbled icon from it would be worse than stopping.
    """
    if data[:8] != _PNG_SIGNATURE:
        raise IconError("not a PNG file: the 8-byte PNG signature is missing.")

    width = height = 0
    idat = bytearray()
    seen_header = False
    offset = 8

    while offset + 8 <= len(data):
        (length,) = struct.unpack_from(">I", data, offset)
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        offset += 12 + length  # length + type + body + CRC

        if kind == b"IHDR":
            if length != 13:
                raise IconError(f"IHDR is {length} bytes, not the required 13.")
            width, height, depth, colour, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", body)
            )
            if depth != 8:
                raise IconError(
                    f"the master PNG is {depth} bits per channel; this tool "
                    f"reads 8-bit images only."
                )
            if colour != _RGBA:
                raise IconError(
                    f"the master PNG is colour type {colour}; this tool reads "
                    f"type {_RGBA} (truecolour with alpha) only, because the "
                    f"icon needs a real alpha channel."
                )
            if compression != 0 or filtering != 0:
                raise IconError(
                    "the master PNG uses a non-standard compression or filter "
                    "method; only the PNG specification's method 0 is read."
                )
            if interlace != 0:
                raise IconError(
                    "the master PNG is interlaced; this tool reads "
                    "non-interlaced images only."
                )
            seen_header = True
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        # Every other chunk is ancillary and deliberately ignored.

    if not seen_header:
        raise IconError("the PNG has no IHDR chunk, so its size is unknown.")
    if not idat:
        raise IconError("the PNG has no IDAT chunk, so it carries no image.")

    raw = zlib.decompress(bytes(idat))
    stride = width * _CHANNELS
    expected = height * (stride + 1)  # one filter-type byte per scanline
    if len(raw) != expected:
        raise IconError(
            f"the PNG's decompressed data is {len(raw)} bytes; a "
            f"{width}x{height} 8-bit RGBA image needs exactly {expected}."
        )

    return width, height, _unfilter(raw, stride, height)


def _unfilter(raw: bytes, stride: int, height: int) -> bytearray:
    """Reverse the per-scanline PNG filters (specification section 9.2)."""
    pixels = bytearray(stride * height)
    previous = bytearray(stride)
    position = 0
    bpp = _CHANNELS

    for row in range(height):
        kind = raw[position]
        position += 1
        line = bytearray(raw[position : position + stride])
        position += stride

        if kind == 0:  # None
            pass
        elif kind == 1:  # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif kind == 3:  # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif kind == 4:  # Paeth
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up = previous[i]
                upper_left = previous[i - bpp] if i >= bpp else 0
                estimate = left + up - upper_left
                da = abs(estimate - left)
                db = abs(estimate - up)
                dc = abs(estimate - upper_left)
                if da <= db and da <= dc:
                    predictor = left
                elif db <= dc:
                    predictor = up
                else:
                    predictor = upper_left
                line[i] = (line[i] + predictor) & 0xFF
        else:
            raise IconError(
                f"scanline {row} uses filter type {kind}; the PNG "
                f"specification defines only 0-4."
            )

        pixels[row * stride : (row + 1) * stride] = line
        previous = line

    return pixels


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------


def _spans(source: int, dest: int) -> list[tuple[int, tuple[float, ...]]]:
    """Per output sample, the source range it covers and its weights.

    Output sample ``d`` covers the half-open source interval
    ``[d * source/dest, (d+1) * source/dest)``. A source sample that is only
    partly inside contributes its overlapping fraction. The weights are
    normalised to sum to 1, so a weighted sum is directly the average.
    """
    if dest > source:
        raise IconError(
            f"this resampler only reduces: asked for {dest} samples from "
            f"{source}."
        )

    scale = source / dest
    spans: list[tuple[int, tuple[float, ...]]] = []

    for index in range(dest):
        low = index * scale
        high = (index + 1) * scale
        first = int(low)
        last = min(int(high - 1e-12), source - 1)
        weights = []
        for sample in range(first, last + 1):
            overlap = min(high, sample + 1) - max(low, sample)
            weights.append(overlap / scale)
        spans.append((first, tuple(weights)))

    return spans


def resample_area(
    pixels: bytes, width: int, height: int, dest_width: int, dest_height: int
) -> bytearray:
    """Area-average downscale of an RGBA buffer, premultiplying alpha.

    Separable: a horizontal pass then a vertical one, which is exact for a box
    filter and turns O(w*h) work per output pixel into O(w+h).
    """
    horizontal = _resample_horizontal(pixels, width, height, dest_width)
    vertical = _resample_vertical(horizontal, dest_width, height, dest_height)
    return _unpremultiply(vertical, dest_width * dest_height)


def _resample_horizontal(
    pixels: bytes, width: int, height: int, dest_width: int
) -> array:
    """Rows resampled to ``dest_width``, as premultiplied float channels."""
    spans = _spans(width, dest_width)
    out = array("d", b"\x00" * (8 * dest_width * height * _CHANNELS))

    for row in range(height):
        row_base = row * width * _CHANNELS
        out_base = row * dest_width * _CHANNELS
        for column, (first, weights) in enumerate(spans):
            red = green = blue = alpha = 0.0
            index = row_base + first * _CHANNELS
            for weight in weights:
                a = pixels[index + 3]
                wa = weight * a
                red += pixels[index] * wa
                green += pixels[index + 1] * wa
                blue += pixels[index + 2] * wa
                alpha += wa
                index += _CHANNELS
            target = out_base + column * _CHANNELS
            out[target] = red
            out[target + 1] = green
            out[target + 2] = blue
            out[target + 3] = alpha

    return out


def _resample_vertical(
    channels: array, width: int, height: int, dest_height: int
) -> array:
    """Columns resampled to ``dest_height``. Already premultiplied."""
    spans = _spans(height, dest_height)
    out = array("d", b"\x00" * (8 * width * dest_height * _CHANNELS))

    for row, (first, weights) in enumerate(spans):
        out_base = row * width * _CHANNELS
        for column in range(width):
            red = green = blue = alpha = 0.0
            index = (first * width + column) * _CHANNELS
            step = width * _CHANNELS
            for weight in weights:
                red += channels[index] * weight
                green += channels[index + 1] * weight
                blue += channels[index + 2] * weight
                alpha += channels[index + 3] * weight
                index += step
            target = out_base + column * _CHANNELS
            out[target] = red
            out[target + 1] = green
            out[target + 2] = blue
            out[target + 3] = alpha

    return out


def _unpremultiply(channels: array, count: int) -> bytearray:
    """Back to 8-bit RGBA, dividing the colour out of the alpha it carries.

    A fully transparent output pixel has no colour to recover and is written as
    transparent black rather than as whatever the division would produce.
    """
    pixels = bytearray(count * _CHANNELS)

    for index in range(count):
        base = index * _CHANNELS
        alpha = channels[base + 3]
        if alpha <= 0.0:
            continue  # already transparent black
        pixels[base] = _to_byte(channels[base] / alpha)
        pixels[base + 1] = _to_byte(channels[base + 1] / alpha)
        pixels[base + 2] = _to_byte(channels[base + 2] / alpha)
        pixels[base + 3] = _to_byte(alpha)

    return pixels


def _to_byte(value: float) -> int:
    """Round to the nearest integer and clamp into 0-255.

    Clamping matters: the area weights sum to 1 in exact arithmetic but to
    1 +/- a few ULPs in doubles, so a run of 255s can average to 255.00000000001.
    """
    rounded = int(value + 0.5)
    if rounded < 0:
        return 0
    if rounded > 255:
        return 255
    return rounded


# ---------------------------------------------------------------------------
# ICO container
# ---------------------------------------------------------------------------


def _dib(pixels: bytes, size: int) -> bytes:
    """One icon image as a 32-bit BGRA DIB, the form an ``.ico`` entry holds.

    The BITMAPINFOHEADER's height is doubled because the structure describes the
    colour bitmap and the AND mask as one image (Microsoft's ICONIMAGE
    documentation). Rows run bottom-up, as in every uncompressed DIB.

    The AND mask is all zeros: every pixel is "not transparent" as far as the
    1-bit mask is concerned, and the real transparency is the alpha channel.
    That is what a 32-bit icon is supposed to do, and Windows has honoured the
    alpha channel over the mask since XP.
    """
    header = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        size,  # biWidth
        size * 2,  # biHeight: colour bitmap plus mask
        1,  # biPlanes
        32,  # biBitCount
        0,  # biCompression = BI_RGB
        0,  # biSizeImage, may be 0 for BI_RGB
        0,  # biXPelsPerMeter
        0,  # biYPelsPerMeter
        0,  # biClrUsed
        0,  # biClrImportant
    )

    colour = bytearray(size * size * 4)
    for row in range(size):
        source = (size - 1 - row) * size * 4  # bottom-up
        target = row * size * 4
        for column in range(size):
            s = source + column * 4
            t = target + column * 4
            colour[t] = pixels[s + 2]  # B
            colour[t + 1] = pixels[s + 1]  # G
            colour[t + 2] = pixels[s]  # R
            colour[t + 3] = pixels[s + 3]  # A

    # 1 bit per pixel, each row padded to a 4-byte boundary.
    mask_stride = ((size + 31) // 32) * 4
    mask = bytes(mask_stride * size)

    return header + bytes(colour) + mask


def build_ico(images: dict[int, bytes]) -> bytes:
    """Assemble an ``.ico`` from ``{size: rgba pixels}``.

    Entries are written smallest first, which is what Windows' own icon editors
    produce; the order carries no meaning, since every consumer reads the
    directory.
    """
    if not images:
        raise IconError("an .ico must contain at least one image.")

    sizes = sorted(images)
    bodies = [_dib(images[size], size) for size in sizes]

    # ICONDIR: reserved, type 1 (icon), image count.
    directory = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(directory) + 16 * len(sizes)

    entries = bytearray()
    for size, body in zip(sizes, bodies):
        if size < 1 or size > 256:
            raise IconError(f"{size} px is outside the 1-256 an .ico can hold.")
        entries += struct.pack(
            "<BBBBHHII",
            size % 256,  # width: 0 means 256
            size % 256,  # height: 0 means 256
            0,  # colours in palette; 0 for a 32-bit image
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(body),
            offset,
        )
        offset += len(body)

    return bytes(directory) + bytes(entries) + b"".join(bodies)


# ---------------------------------------------------------------------------
# The build step
# ---------------------------------------------------------------------------


def render_sizes(
    pixels: bytes, width: int, height: int, sizes=ICON_SIZES
) -> dict[int, bytes]:
    """Every requested size, derived from the master.

    Each size is reduced from the largest already-rendered size that is a clean
    starting point rather than from the 1024 px master every time. Reducing
    1024 -> 256 once and then 256 -> 128, 64, 48, 32, 16 visits about a
    twentieth as many source pixels as six independent reductions from 1024, and
    an area average of an area average over a whole number of samples is the
    same thing as one area average.
    """
    if width != height:
        raise IconError(
            f"the master artwork is {width}x{height}; an icon is square, and "
            f"cropping it is the owner's decision, not this tool's."
        )

    rendered: dict[int, bytes] = {}
    source, source_size = pixels, width

    for size in sorted(sizes, reverse=True):
        if size > source_size:
            raise IconError(
                f"cannot render {size} px from a {source_size} px master: this "
                f"tool only reduces, and upscaling would invent detail."
            )
        rendered[size] = bytes(resample_area(source, source_size, source_size, size, size))
        # The largest rendered size becomes the source for the smaller ones.
        if source_size == width:
            source, source_size = rendered[size], size

    return rendered


def generate(master: Path = MASTER_PNG, output: Path = DEFAULT_OUTPUT) -> Path:
    """Read the master, render every size, write the ``.ico``. Returns its path.

    Staged and renamed, like every other file this project writes: a build
    interrupted halfway leaves either the previous icon or nothing, never a
    truncated one that Explorer would cache (docs/DESIGN.md section 7).
    """
    if not master.is_file():
        raise IconError(f"the master artwork is missing: {master}")

    width, height, pixels = decode_png_rgba8(master.read_bytes())
    data = build_ico(render_sizes(pixels, width, height))

    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.with_name(output.name + ".partial")
    staged.write_bytes(data)
    staged.replace(output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--master", type=Path, default=MASTER_PNG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args(argv)

    try:
        written = generate(arguments.master, arguments.output)
    except IconError as error:
        print(f"icon build refused: {error}", file=sys.stderr)
        return 1

    print(
        f"wrote {written} "
        f"({written.stat().st_size:,} bytes, "
        f"{', '.join(f'{s}x{s}' for s in ICON_SIZES)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
