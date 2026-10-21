"""The monthly tripwire, driven offline against fake answers.

``tools/nsrs_tripwire.py`` runs once a month on the owner's machine, unattended,
and its whole value is in telling three outcomes apart: QUIET (every answer
positively matches the frozen expectation), TRIPPED (an answer that is an
answer, and differs) and COULD NOT CHECK (anything else). A tripwire that read
a failure as quiet would be silent exactly when it is blind - the fail-open
shape docs/method/TOOLING.md records for NGS's own servers - so most of what is
pinned here is that third outcome.

No network: every test hands ``main`` a fetch function. Until the WGS 84 build
the tool had no tests at all; the HTDP probe (docs/REFREEZE-HTDP.md) is the
reason these exist, and the older probes are pinned beside it in the same
style.
"""

from __future__ import annotations

import http.client
import json
import urllib.error

import pytest

from tools import nsrs_tripwire as tripwire

FROZEN = tripwire.FROZEN_HTDP_COMMIT

# A real-shaped answer from GitHub's commit endpoint, trimmed to the fields the
# probe reads (GET /repos/{owner}/{repo}/commits/{ref}).
HTDP_QUIET = json.dumps(
    {
        "sha": FROZEN,
        "commit": {
            "committer": {"date": "2025-04-07T15:04:21Z"},
            "message": "HTDP v3.6.0",
        },
    }
)
MOVED = "0123456789abcdef0123456789abcdef01234567"
HTDP_MOVED = json.dumps(
    {
        "sha": MOVED,
        "commit": {
            "committer": {"date": "2027-02-01T00:00:00Z"},
            "message": "HTDP v3.7.0\n\nnew velocity grid",
        },
    }
)
ORG_QUIET = json.dumps([{"name": f"repo{n}"} for n in range(tripwire.FROZEN_REPO_COUNT)])


def answers(**overrides):
    """A fetch that answers every probe quietly, except where overridden.

    ``overrides`` maps a URL to a body string or to an exception instance to
    raise, so each test changes exactly one probe.
    """
    table = {url: fragment for _name, url, fragment in tripwire.PROBES}
    table[tripwire.GITHUB_ORG_URL] = ORG_QUIET
    table[tripwire.HTDP_HEAD_URL] = HTDP_QUIET
    table.update(overrides)

    def fetch(url):
        value = table[url]
        if isinstance(value, BaseException):
            raise value
        return value

    return fetch


def run(tmp_path, fetch):
    notices = []
    code = tripwire.main(
        fetch=fetch, report_dir=tmp_path, today="2027-03-01", notify=notices.append
    )
    report = (tmp_path / "tripwire-2027-03-01.txt").read_text(encoding="utf-8")
    review = tmp_path / "REVIEW-NEEDED.txt"
    return code, report, review.read_text(encoding="utf-8") if review.exists() else None, notices


# ==========================================================================
# The frozen value is the transcribed one.
# ==========================================================================


def test_the_frozen_htdp_commit_is_the_commit_the_program_transcribes():
    """Two copies, deliberately, held equal - the self-test anchors' idiom.

    The tool runs unattended and must not depend on ``michspc`` importing
    cleanly, so it carries the literal; ``htdp_data.HTDP_COMMIT`` is the
    program's own statement of what it transcribed. A re-freeze that moves one
    and not the other fails here.
    """
    from michspc.spc import htdp_data

    assert tripwire.FROZEN_HTDP_COMMIT == htdp_data.HTDP_COMMIT
    assert tripwire.FROZEN_HTDP_COMMIT == "59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c"
    assert htdp_data.HTDP_VERSION in tripwire.FROZEN_HTDP_RELEASE
    assert tripwire.HTDP_HEAD_URL == (
        "https://api.github.com/repos/noaa-ngs/HTDP/commits/HEAD"
    )


# ==========================================================================
# Quiet, and the HTDP probe's two answers.
# ==========================================================================


def test_a_quiet_month_is_quiet_and_says_so_for_every_probe(tmp_path):
    code, report, review, notices = run(tmp_path, answers())

    assert code == 0
    assert review is None and notices == []
    assert report.count("  quiet         ") == len(tripwire.PROBES) + 2
    assert "HTDP (noaa-ngs/HTDP default-branch head) (59fdbe6b)" in report
    assert "PROBE FAILED" not in report and "TRIPPED" not in report


def test_a_new_htdp_head_trips_the_wire_and_names_the_document(tmp_path):
    """The HTDP tripwire firing: the owner is told, the same way the others tell him."""
    code, report, review, notices = run(
        tmp_path, answers(**{tripwire.HTDP_HEAD_URL: HTDP_MOVED})
    )

    assert code == 1
    assert "*** TRIPPED   HTDP" in report
    assert MOVED in review and FROZEN in review
    assert "2027-02-01T00:00:00Z" in review and "HTDP v3.7.0" in review
    assert "docs/REFREEZE-HTDP.md" in review
    assert notices == [review]


def test_a_head_differing_only_in_its_last_character_still_trips(tmp_path):
    """The whole id is compared - never a prefix, never the short form."""
    near = FROZEN[:-1] + ("0" if FROZEN[-1] != "0" else "1")
    code, report, _review, _notices = run(
        tmp_path,
        answers(**{tripwire.HTDP_HEAD_URL: json.dumps({"sha": near})}),
    )

    assert code == 1
    assert "*** TRIPPED   HTDP" in report


def test_a_trip_outranks_a_probe_failure(tmp_path):
    """Exit 1 when anything tripped, even if another probe could not check."""
    code, report, review, _notices = run(
        tmp_path,
        answers(
            **{
                tripwire.HTDP_HEAD_URL: HTDP_MOVED,
                tripwire.GITHUB_ORG_URL: urllib.error.URLError("down"),
            }
        ),
    )

    assert code == 1
    assert "PROBE FAILED  github" in report
    assert review is not None


# ==========================================================================
# Could not check: every way an answer is not an answer.
# ==========================================================================


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.HTTPError(
            tripwire.HTDP_HEAD_URL, 403, "rate limit exceeded", None, None
        ),
        urllib.error.URLError("[Errno 11001] getaddrinfo failed"),
        TimeoutError("timed out"),
        http.client.IncompleteRead(b"{\"sha\": \"59fd"),
    ],
    ids=["http-403", "dns", "timeout", "cut-mid-body"],
)
def test_an_htdp_fetch_error_is_could_not_check(tmp_path, failure):
    code, report, review, notices = run(
        tmp_path, answers(**{tripwire.HTDP_HEAD_URL: failure})
    )

    assert code == 2
    assert "PROBE FAILED  HTDP" in report
    assert "quiet         HTDP" not in report
    assert review is None and notices == []


@pytest.mark.parametrize(
    "body",
    [
        # GitHub's own refusal object: JSON, and no commit in it.
        json.dumps({"message": "API rate limit exceeded for 203.0.113.7."}),
        # This container's proxy answered exactly this shape, 2026-10-21.
        json.dumps({"message": "GitHub access to this repository is not enabled"}),
        "<html><body>Sign in to the hotel Wi-Fi</body></html>",
        "",
        json.dumps([{"sha": FROZEN}]),
        json.dumps({"sha": FROZEN.upper()}),
        json.dumps({"sha": FROZEN[:7]}),
        json.dumps({"sha": None}),
    ],
    ids=[
        "rate-limit-object",
        "proxy-object",
        "captive-portal-html",
        "empty",
        "a-list",
        "uppercase-sha",
        "short-sha",
        "null-sha",
    ],
)
def test_an_htdp_answer_that_is_not_a_commit_is_could_not_check(tmp_path, body):
    """Fail-closed on shape: neither quiet nor tripped, because it answered nothing.

    The uppercase and short forms are refused rather than normalised: GitHub
    returns the full lowercase id, so anything else is not its answer.
    """
    code, report, review, _notices = run(
        tmp_path, answers(**{tripwire.HTDP_HEAD_URL: body})
    )

    assert code == 2
    assert "PROBE FAILED  HTDP" in report
    assert review is None


@pytest.mark.parametrize(
    "body",
    [
        json.dumps({"message": "API rate limit exceeded"}),
        json.dumps([{"full_name": "noaa-ngs/HTDP"}] * tripwire.FROZEN_REPO_COUNT),
        "<html>portal</html>",
    ],
    ids=["error-object", "no-names", "html"],
)
def test_an_org_listing_that_is_not_a_listing_is_could_not_check(tmp_path, body):
    """The org probe, held to the same rule (it used to crash on an error object).

    A JSON OBJECT iterated as though it were the listing yields its keys; the
    old code then called ``.get`` on a string and the whole tripwire died
    without writing its report - exit 1, the TRIPPED code, with no notice.
    """
    code, report, review, _notices = run(
        tmp_path, answers(**{tripwire.GITHUB_ORG_URL: body})
    )

    assert code == 2
    assert "PROBE FAILED  github" in report
    assert review is None


def test_a_new_repository_in_the_org_still_trips(tmp_path):
    grown = json.dumps(
        [{"name": f"repo{n}"} for n in range(tripwire.FROZEN_REPO_COUNT + 1)]
    )
    code, report, review, _notices = run(
        tmp_path, answers(**{tripwire.GITHUB_ORG_URL: grown})
    )

    assert code == 1
    assert "*** TRIPPED   github (10 repos)" in report
    assert "noaa-ngs GitHub org changed" in review


def test_an_ngs_refusal_that_changed_trips_and_a_dead_host_does_not(tmp_path):
    """The three NGS probes: a different body trips, a fetch error does not."""
    _name, url, _fragment = tripwire.PROBES[0]

    code, report, review, _notices = run(tmp_path, answers(**{url: '{"lat": 43.0}'}))
    assert code == 1
    assert "*** TRIPPED   frame bridge" in report

    (tmp_path / "REVIEW-NEEDED.txt").unlink()
    code, report, review, _notices = run(
        tmp_path, answers(**{url: http.client.RemoteDisconnected("closed")})
    )
    assert code == 2
    assert "PROBE FAILED  frame bridge" in report
    assert review is None


def test_the_htdp_probe_reads_the_documented_fields_and_nothing_else():
    sha, description = tripwire.htdp_head(HTDP_MOVED)
    assert sha == MOVED
    assert description == "2027-02-01T00:00:00Z, 'HTDP v3.7.0'"

    sha, description = tripwire.htdp_head(json.dumps({"sha": FROZEN}))
    assert sha == FROZEN
    assert description == "date ?, '(no message)'"
