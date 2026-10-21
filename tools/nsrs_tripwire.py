"""The monthly NSRS tripwire: has NGS published what the deferrals wait on?

The two standing deferral markers (docs/DEFERRED-NATRF2022-BRIDGE.md and
docs/DEFERRED-NAPGD2022.md) each list reopen conditions whose common thread
is a probe this script re-runs, and the HTDP re-freeze obligation
(docs/REFREEZE-HTDP.md) adds one of its own:

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
  5. Has NGS's HTDP moved?  MCX's WGS 84 and ITRF conversions are a
     transcription of HTDP v3.6.0, github.com/noaa-ngs/HTDP commit
     59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c (2025-04-07), and every anchor
     the suite holds them to is that commit's output.  A different head on
     the repository's default branch is the HTDP tripwire firing: it reopens
     the anchors (docs/REFREEZE-HTDP.md).

Run monthly by a Windows scheduled task (see the registration command in
docs/DEFERRED-NATRF2022-BRIDGE.md's tripwire section).  Writes a dated
report under review/tripwire/ next to this repo; on ANY change from the
frozen expectations it also writes review/tripwire/REVIEW-NEEDED.txt and
shows a message box so the owner cannot miss it.  Quiet months leave only
the dated log line.  Exit code: 0 quiet, 1 tripped, 2 probe failure
(network down etc. - reported, never mistaken for a trip, and never for a
quiet month either).

**Fail-closed, the way docs/method/TOOLING.md's NGS hazards require.** A
probe is "quiet" only when the answer positively matches the frozen
expectation: a JSON object whose ``error`` field carries the frozen refusal
text, a list of exactly the frozen number of repositories, or a well-formed
40-hex commit equal to the frozen one.  A fetch that errors, a body that is
not the JSON shape the API documents (a captive portal's HTML, an empty
body, an empty object, a proxy's error object or a rate-limit message where
GitHub's listing or commit is expected), or a commit field that is not a
commit, is "could not check" - PROBE FAILED, exit 2 - never quiet, and never
silently skipped.  Only a well-formed answer that differs from the frozen
one TRIPS: for probes 1 to 3, a non-empty JSON object that is not the frozen
refusal (closing gate of the WGS 84 build, finding L5: those three probes
used to look for the refusal text anywhere in the body, so a captive
portal's page tripped the wire and raised the message box).

Deliberately stdlib-only and read-only toward NGS and GitHub: five GETs a
month.
"""

from __future__ import annotations

import datetime as _dt
import http.client
import json
import re
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

HTDP_HEAD_URL = "https://api.github.com/repos/noaa-ngs/HTDP/commits/HEAD"
"""GitHub's commit endpoint for ``HEAD``, which resolves to the head of the
repository's DEFAULT branch, whatever it is named (``main`` on 2026-10-21,
read with ``git ls-remote --symref``), so a renamed default branch is
followed rather than missed."""

FROZEN_HTDP_COMMIT = "59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c"
"""HTDP v3.6.0 (htdp.f:27-28, "April 7, 2025"), tagged ``v.3.6.0`` - the
commit michspc/spc/htdp_data.py transcribes. A second copy of
``htdp_data.HTDP_COMMIT``, deliberately: this tool runs unattended once a
month and must not depend on the program importing cleanly, so it carries
the literal and tests/test_nsrs_tripwire.py pins the two equal with ``==``."""

FROZEN_HTDP_RELEASE = "v3.6.0, 2025-04-07"

_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")

FETCH_FAILURES = (OSError, http.client.HTTPException, ValueError)
"""Everything a GET and a JSON parse can raise for a reason that is not an
answer: urllib's HTTP and URL errors and timeouts (OSError), a connection cut
mid-body (http.client.HTTPException, which is NOT an OSError), and a body that
is not JSON (ValueError). Each one is "could not check"."""


class ProbeFailed(Exception):
    """The probe got an answer, and it is not one it can read. Could not check."""


def _fetch(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "mcx-nsrs-tripwire (monthly; 5 requests)"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return response.read().decode("utf-8", "replace")


def ngs_refusal_unchanged(body: str, expected_fragment: str) -> bool:
    """Whether an NCAT or geoid-service answer is still the frozen refusal.

    True: the body is a JSON object whose ``error`` field contains the frozen
    refusal text (the shape frozen in review/nsrs-n0/raw, e.g.
    ``{"error": "Invalid outputDatum"}``) - quiet. False: a non-empty JSON
    object that is not that refusal - an answer, and a different one, so the
    probe trips. Anything else is not an answer to the question and raises:
    a body that is not JSON (a captive portal's HTML, an empty body) raises
    ``ValueError`` from the parse, and JSON that is not an object, or an
    empty object (the beta host's fail-open ``{}``, TOOLING.md), raises
    ``ProbeFailed``. Both are "could not check".
    """
    data = json.loads(body)
    if not isinstance(data, dict) or not data:
        raise ProbeFailed(
            f"the answer is not the JSON object the service documents; it "
            f"begins {body[:200]!r}"
        )
    error = data.get("error")
    return isinstance(error, str) and expected_fragment in error


def github_repo_names(body: str) -> list[str]:
    """The organisation's repository names, or ``ProbeFailed`` if the body is not a listing.

    GitHub documents the listing as a JSON array of objects each carrying a
    string ``name``. Anything else - an error object such as a rate-limit
    message, which arrives as a JSON OBJECT - is refused here rather than
    iterated: iterating an object yields its keys, and counting those would
    compare a message's field count against the frozen repository count.
    """
    data = json.loads(body)
    if not isinstance(data, list) or not all(
        isinstance(r, dict) and isinstance(r.get("name"), str) for r in data
    ):
        raise ProbeFailed(
            f"the organisation listing is not a JSON array of repositories; "
            f"it begins {body[:200]!r}"
        )
    return sorted(r["name"] for r in data)


def htdp_head(body: str) -> tuple[str, str]:
    """``(sha, description)`` of HTDP's default-branch head, or ``ProbeFailed``.

    Strict: the body must be a JSON object whose ``sha`` is a 40-character
    lowercase hexadecimal commit id. A body without one (GitHub's own error
    objects carry ``message`` and no ``sha``) is not an answer to the
    question, so it can neither match the frozen commit nor trip on it.
    """
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ProbeFailed(f"the commit endpoint answered {body[:200]!r}")
    sha = data.get("sha")
    if not isinstance(sha, str) or not _COMMIT_SHA.fullmatch(sha):
        raise ProbeFailed(
            f"the commit endpoint's answer carries no commit id (sha={sha!r}); "
            f"it begins {body[:200]!r}"
        )
    commit = data.get("commit") if isinstance(data.get("commit"), dict) else {}
    committer = commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
    date = committer.get("date") if isinstance(committer.get("date"), str) else "date ?"
    message = commit.get("message") if isinstance(commit.get("message"), str) else ""
    first_line = message.splitlines()[0] if message else "(no message)"
    return sha, f"{date}, {first_line!r}"


def probe_htdp(fetch=None) -> tuple[str, str, str]:
    """``(outcome, log line, detail)``; outcome is "quiet", "tripped" or "failed"."""
    name = "HTDP (noaa-ngs/HTDP default-branch head)"
    try:
        sha, description = htdp_head((fetch or _fetch)(HTDP_HEAD_URL))
    except (*FETCH_FAILURES, ProbeFailed) as error:
        return (
            "failed",
            f"  PROBE FAILED  {name}: {error}",
            f"{name}: probe failed ({error})",
        )
    if sha == FROZEN_HTDP_COMMIT:
        return "quiet", f"  quiet         {name} ({sha[:8]})", ""
    return (
        "tripped",
        f"  *** TRIPPED   {name} ({sha[:8]})",
        f"NGS's HTDP has moved: the default branch of noaa-ngs/HTDP is now at "
        f"{sha} ({description}), where MCX transcribes {FROZEN_HTDP_COMMIT} "
        f"({FROZEN_HTDP_RELEASE}). Every HTDP anchor MCX is held to is that "
        f"commit's output. Read docs/REFREEZE-HTDP.md before anything else.",
    )


def main(fetch=None, report_dir: Path | None = None, today: str | None = None,
         notify=None) -> int:
    """Run every probe. The arguments exist for the suite; the task passes none."""
    fetch = fetch or _fetch
    report_dir = report_dir or REPORT_DIR
    notify = notify or _message_box
    report_dir.mkdir(parents=True, exist_ok=True)
    today = today or _dt.date.today().isoformat()
    lines: list[str] = [f"NSRS tripwire, {today}"]
    tripped: list[str] = []
    failed: list[str] = []

    for name, url, expected_fragment in PROBES:
        try:
            body = fetch(url)
            unchanged = ngs_refusal_unchanged(body, expected_fragment)
        except (*FETCH_FAILURES, ProbeFailed) as error:
            failed.append(f"{name}: probe failed ({error})")
            lines.append(f"  PROBE FAILED  {name}: {error}")
            continue
        if unchanged:
            lines.append(f"  quiet         {name}")
        else:
            tripped.append(f"{name}: NGS no longer answers the frozen "
                           f"refusal. Response now begins: {body[:200]!r}")
            lines.append(f"  *** TRIPPED   {name}")

    try:
        names = github_repo_names(fetch(GITHUB_ORG_URL))
        if len(names) != FROZEN_REPO_COUNT:
            tripped.append(
                f"noaa-ngs GitHub org changed: {len(names)} repos vs the "
                f"frozen {FROZEN_REPO_COUNT}. Now: {', '.join(names)}"
            )
            lines.append(f"  *** TRIPPED   github ({len(names)} repos)")
        else:
            lines.append(f"  quiet         github ({FROZEN_REPO_COUNT} repos)")
    except (*FETCH_FAILURES, ProbeFailed) as error:
        failed.append(f"github: probe failed ({error})")
        lines.append(f"  PROBE FAILED  github: {error}")

    outcome, line, detail = probe_htdp(fetch)
    lines.append(line)
    if outcome == "tripped":
        tripped.append(detail)
    elif outcome == "failed":
        failed.append(detail)

    report = "\n".join(lines) + "\n"
    (report_dir / f"tripwire-{today}.txt").write_text(report, encoding="utf-8")

    if tripped:
        notice = (
            f"NSRS TRIPWIRE FIRED ({today})\n\n" + "\n\n".join(tripped) +
            "\n\nRead docs/DEFERRED-NATRF2022-BRIDGE.md and "
            "docs/DEFERRED-NAPGD2022.md for what reopens (and "
            "docs/REFREEZE-HTDP.md if HTDP moved), and re-run the "
            "frozen capture harnesses before believing anything."
        )
        (report_dir / "REVIEW-NEEDED.txt").write_text(notice, encoding="utf-8")
        notify(notice)
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
