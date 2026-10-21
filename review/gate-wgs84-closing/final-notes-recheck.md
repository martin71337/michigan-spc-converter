# Closing gate, WGS 84 build: recheck of the release-notes fix

**Reviewer:** an independent Opus reviewer. I did not write the notes or the fix.

**Scope:** the uncommitted `git diff docs/RELEASE-NOTES-0.8.0.md` against the
F1, F2 and INFO items of `final-notes-check.md`, plus a whole-file search for
any remaining claim that the closing gate is outstanding. Nothing else was
reviewed. The only file I wrote is this one.

## The three items

| Item | Resolved | Evidence |
|---|---|---|
| F1: the "still to do" list named the closing gate | **Yes** | The bullet now reads "**The release build**: `py tools/build_release.py --acknowledge-ngs-beta` on the owner's machine." This agrees with lines 5-6 ("has run, and its findings are fixed") and with the Verified section (lines 224-234). |
| F2: "in either case; both are sentences" with three items | **Yes** | It now reads "No number was ever wrong in any of them; all are sentences in the job record". All three items are job-record sentences, so the plural is true. |
| INFO: item 3 left out the geoid-swap phrase | **Yes** | Item 3 now adds "the geoid model the Z column and the factors are stated against" when the job changed geoid models. Checked against the code below. |

**Code check for the INFO text.** The released 0.7.1 tree (`7494726`,
`report.py:1832-1837`) writes "the geoid model the Z column and" / "the factors
are stated against." under `if vertical and swap_models is not None`, which
sits inside the FILES WRITTEN section. The current `report.py:2722-2729`
branches on `zoneless` in that same block and writes "the elevation factor are
stated against." for a zone-less job. So the quoted phrase is exact. It was
present in released records. The condition "when the job changed geoid models"
matches `job.geoid_swap_models` (an identity datum with two different models).
The closing clause, "They now name the elevation factor", is true for this
branch as well.

## New-text hygiene

- I found no new false or self-contradictory sentence.
- The whole file has 0 U+2014 and 0 U+2013 characters. Its only non-ASCII
  character is U+21C4 on line 131, which predates this diff.
- There is no BOM, no CRLF and no bare CR.

## Remaining "gate outstanding" text

I searched the file for `closing`, `gate`, `outstanding`, `not yet` and
`still to`. Every hit says the closing gate ran (lines 5-6 and 227-231), or it
concerns the build gates (lines 220-221). The one remaining forward-looking
sentence, "A Codex re-confirmation on the owner's machine is his option", is an
optional extra. It does not claim the gate is pending.

VERDICT: APPROVED
