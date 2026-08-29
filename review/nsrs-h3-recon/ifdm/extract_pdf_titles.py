"""Read the title page of every captured NGS report and search each for the
terms H3 cares about.

A report number is not a title. The H3 brief assumed NOAA TR NOS NGS 63 is the
NATRF2022 defining document; the beta NCAT page cites 63 for NADCON 5.0. This
script settles that from the PDFs themselves, and proves presence or absence of
IFDM2022 / NATRF2022 / EPP text across the recent library.

Run with an interpreter that has pypdf.
"""

from __future__ import annotations

import json
import os
import re
import sys

from pypdf import PdfReader

HERE = os.path.dirname(os.path.abspath(__file__))
PUBS = os.path.join(HERE, "raw", "pubs")
OUT = os.path.join(HERE, "raw", "pubs")

TERMS = ["IFDM", "NATRF2022", "PATRF2022", "MATRF2022", "CATRF2022",
         "Euler Pole", "EPP2022", "intra-frame", "intraframe", "ITRF2020",
         "NAD83(2011)", "Helmert", "epoch"]


def main():
    rows = []
    lines = []
    for fn in sorted(os.listdir(PUBS)):
        if not fn.lower().endswith(".pdf"):
            continue
        path = os.path.join(PUBS, fn)
        try:
            r = PdfReader(path)
        except Exception as exc:
            lines.append("%s  UNREADABLE: %s" % (fn, exc))
            continue
        title_text = ""
        for i in range(min(3, len(r.pages))):
            try:
                title_text += r.pages[i].extract_text() or ""
            except Exception:
                pass
        # NGS title pages use U+2010/non-breaking spaces; normalise for reading.
        flat = re.sub(r"[‐‑ ​]", lambda m:
                      "-" if m.group() in "‐‑" else " ", title_text)
        flat = re.sub(r"\s+", " ", flat).strip()
        full = []
        for pg in r.pages:
            try:
                full.append(pg.extract_text() or "")
            except Exception:
                full.append("")
        body = "\n".join(full)
        counts = {t: len(re.findall(re.escape(t), body, re.I)) for t in TERMS}
        rows.append({
            "file": fn,
            "pages": len(r.pages),
            "pdf_title_metadata": (r.metadata or {}).get("/Title"),
            "title_page_text": flat[:600],
            "term_counts": counts,
        })
        lines.append("=" * 78)
        lines.append("%s   %d pages" % (fn, len(r.pages)))
        lines.append("  /Title metadata: %s" % (r.metadata or {}).get("/Title"))
        lines.append("  title page: %s" % flat[:400])
        lines.append("  term counts: %s" % ", ".join(
            "%s=%d" % (k, v) for k, v in counts.items() if v))
        if not any(counts.values()):
            lines.append("  term counts: (none of the H3 terms appear)")
        lines.append("")
    txt = os.path.join(OUT, "pub_titles_and_terms.txt")
    with open(txt, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    js = os.path.join(OUT, "pub_titles_and_terms.json")
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows, fh, indent=2, sort_keys=True)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(lines))
    print("wrote", txt)
    print("wrote", js)


if __name__ == "__main__":
    main()
