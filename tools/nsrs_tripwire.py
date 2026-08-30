"""The monthly NSRS tripwire: has NGS published what the deferrals wait on?

The two standing deferral markers (docs/DEFERRED-NATRF2022-BRIDGE.md and
docs/DEFERRED-NAPGD2022.md) each list reopen conditions whose common thread
is a probe this script re-runs:

  1. Does any NCAT REST endpoint now accept a NATRF2022 token?  Today both
     hosts answer {"error": "Invalid outputDatum"} (review/nsrs-n0, frozen
     2026-08-28).  An answer that is not that refusal is the frame-bridge
     tripwire firing.
  2. Does the REST endpoint now accept NAPGD2022 as a vertical datum?
     Today: {"error": "Invalid output vertical Datum"}.  Anything else is
     the vertical tripwire firing.
  3. Does the geoid service now carry a model beyond 14 (GEOID18), i.e.
     GEOID2022?  Today model 15 answers "No suitable Geoid model found".
  4. Has the noaa-ngs GitHub organisation gained a repository since the
     frozen snapshot (9 repos, 2026-08-29)?  The NATRF2022 page promises
     the developer test dataset "on GitHub after completing internal
     review" - a new repo is the likeliest form.

Run monthly by a Windows scheduled task (see the registration command in
docs/DEFERRED-NATRF2022-BRIDGE.md's tripwire section).  Writes a dated
report under review/tripwire/ next to this repo; on ANY change from the
frozen expectations it also writes review/tripwire/REVIEW-NEEDED.txt and
shows a message box so the owner cannot miss it.  Quiet months leave only
the dated log line.  Exit code: 0 quiet, 1 tripped, 2 probe failure
(network down etc. - reported, never mistaken for a trip).

Deliberately stdlib-only and read-only toward NGS: four GETs a month.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "review" / "tripwire"

TIMEOUT_S = 60

# The frozen expectations, verbatim from review/nsrs-n0 (2026-08-28/29).
PROBES = (
    (
        "frame bridge (NATRF2022 token on the REST API)",
        "https://geodesy.noaa.gov/api/ncat/llh?lat=43.0&lon=-84.5"
        "&inDatum=NAD83(2011)&outDatum=NATRF2022",
        "Invalid outputDatum",
    ),
    (
        "vertical product (NAPGD2022 vertical-datum token)",
        "https://geodesy.noaa.gov/api/ncat/llh?lat=43.0&lon=-84.5"
        "&inDatum=NAD83(2011)&outDatum=NAD83(2011)&orthoHt=200.0"
        "&inVertDatum=NAVD88&outVertDatum=NAPGD2022",
        "Invalid output vertical Datum",
    ),
    (
        "geoid service (a model beyond GEOID18's id 14)",
        "https://geodesy.noaa.gov/api/geoid/ght?lat=43.0&lon=-84.5&model=15",
        "No suitable Geoid model found",
    ),
)

GITHUB_ORG_URL = "https://api.github.com/orgs/noaa-ngs/repos?per_page=100"
FROZEN_REPO_COUNT = 9  # measured 2026-08-29, review/nsrs-h3-recon


def _fetch(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "mcx-nsrs-tripwire (monthly; 4 requests)"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return response.read().decode("utf-8", "replace")


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    lines: list[str] = [f"NSRS tripwire, {today}"]
    tripped: list[str] = []
    failed: list[str] = []

    for name, url, expected_fragment in PROBES:
        try:
            body = _fetch(url)
        except OSError as error:
            failed.append(f"{name}: probe failed ({error})")
            lines.append(f"  PROBE FAILED  {name}: {error}")
            continue
        if expected_fragment in body:
            lines.append(f"  quiet         {name}")
        else:
            tripped.append(f"{name}: NGS no longer answers the frozen "
                           f"refusal. Response now begins: {body[:200]!r}")
            lines.append(f"  *** TRIPPED   {name}")

    try:
        repos = json.loads(_fetch(GITHUB_ORG_URL))
        names = sorted(r.get("name", "?") for r in repos)
        if len(names) != FROZEN_REPO_COUNT:
            tripped.append(
                f"noaa-ngs GitHub org changed: {len(names)} repos vs the "
                f"frozen {FROZEN_REPO_COUNT}. Now: {', '.join(names)}"
            )
            lines.append(f"  *** TRIPPED   github ({len(names)} repos)")
        else:
            lines.append("  quiet         github (9 repos)")
    except (OSError, ValueError) as error:
        failed.append(f"github: probe failed ({error})")
        lines.append(f"  PROBE FAILED  github: {error}")

    report = "\n".join(lines) + "\n"
    (REPORT_DIR / f"tripwire-{today}.txt").write_text(report, encoding="utf-8")

    if tripped:
        notice = (
            f"NSRS TRIPWIRE FIRED ({today})\n\n" + "\n\n".join(tripped) +
            "\n\nRead docs/DEFERRED-NATRF2022-BRIDGE.md and "
            "docs/DEFERRED-NAPGD2022.md for what reopens, and re-run the "
            "frozen capture harnesses before believing anything."
        )
        (REPORT_DIR / "REVIEW-NEEDED.txt").write_text(notice, encoding="utf-8")
        _message_box(notice)
        return 1
    if failed:
        return 2
    return 0


def _message_box(text: str) -> None:
    """A visible notice; failure to show it must not eat the report."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0, text, "MCX - NGS has published something", 0x40
        )
    except Exception:  # noqa: BLE001 - the report file is the real record
        pass


if __name__ == "__main__":
    sys.exit(main())
