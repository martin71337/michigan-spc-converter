Byte-identity evidence for the ellipsoid-height feature (DESIGN.md #54)
=======================================================================

Run by the session lead on 2026-08-11, independently of the closing gate, to
check the feature's load-bearing regression promise: that a job which does not
opt in produces exactly what v0.5.0 produced.

Method
------
`digest_jobs.py` writes nine ORTHOMETRIC job archives - zone-to-zone and
State-Plane-to-geodetic in all three units, a horizontal+vertical NGVD29 ->
NAVD88 job, a vertical-only job, and a GEOID12B -> GEOID18 swap - each over the
same three rows, one of which carries a populated Z, one an exactly-zero Z and
one a blank Z. Every member of every archive is SHA-256'd.

The same script was run twice: once inside a detached git worktree at tag
v0.5.0, once at HEAD. Nothing in the script mentions the new setting, so both
runs exercise the default.

Result
------
27 members compared, 27 identical apart from two harness-caused differences:

  * the job record's generation timestamp, which differs between any two runs
    of the same code, and
  * the input file and output folder paths, which differ because the two runs
    were written to out050/ and outhead/ respectively.

All eighteen CSV members - every clean PNEZD export and every audit CSV -
hashed identically outright, with no exclusions.

The comparison is reproducible: recreate the worktree, run the script into two
directories, and diff the digest lists.
