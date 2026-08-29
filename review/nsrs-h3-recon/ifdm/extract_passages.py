"""Pull, verbatim and with page numbers, the passages H3's math rests on.

Usage:  extract_passages.py <pdf> [<out-stem>]

Prints every page whose text matches one of the H3 terms, in full, with the
PDF's own page number and the sheet label printed on the page where one can be
found. Verbatim: no summarising, no reflowing beyond what pypdf's extractor
does, because the point of the capture is to be quotable.

Run with an interpreter that has pypdf.
"""

from __future__ import annotations

import os
import re
import sys

from pypdf import PdfReader

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "raw", "pubs")

PATTERNS = [
    r"IFDM", r"intra-?frame", r"NATRF2022", r"EPP2022", r"Euler Pole",
    r"NAD ?83\(2011\)", r"Helmert", r"14-parameter", r"14 parameter",
    r"transformation", r"epoch",
]


def main():
    pdf = sys.argv[1]
    stem = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(
        os.path.basename(pdf))[0] + "_passages"
    rx = re.compile("|".join(PATTERNS), re.I)
    r = PdfReader(pdf)
    chunks = []
    for i, pg in enumerate(r.pages):
        try:
            t = pg.extract_text() or ""
        except Exception as exc:
            chunks.append("### PDF page %d -- extraction failed: %s" % (i + 1, exc))
            continue
        hits = sorted(set(m.group(0) for m in rx.finditer(t)))
        if not hits:
            continue
        chunks.append("#" * 74)
        chunks.append("### PDF page %d (of %d)   matches: %s"
                      % (i + 1, len(r.pages), ", ".join(hits)))
        chunks.append("#" * 74)
        chunks.append(t)
        chunks.append("")
    out = os.path.join(OUT, stem + ".txt")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("Verbatim page extraction from %s\n" % os.path.basename(pdf))
        fh.write("pages: %d;  matched pages: %d\n\n"
                 % (len(r.pages), sum(1 for c in chunks if c.startswith("### PDF page"))))
        fh.write("\n".join(chunks))
    print("wrote", out)


if __name__ == "__main__":
    main()
