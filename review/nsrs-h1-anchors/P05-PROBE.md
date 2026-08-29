# P05 probe — is `frame_p05` real beta NCAT behaviour or a capture artifact?

**Capture date: 2026-08-29**, owner's Windows machine. Source
`https://beta.ngs.noaa.gov/NCAT/` (beta NCAT v3.0), same harness, same echo
checks, throttled at 1/s. Six requests, one session. All six verified: result
block present, `Reference Frame` in and out equal to the pair asked for, and
NCAT's echo of the input position equal to what was sent.

Reproduce with `py -3 capture_p05_probe.py`.

Datum pair throughout: **`NAD83(2011) epoch 2010.00` → `NATRF2022 epoch
2020.00`**, no zone forced.

This file records values only. It draws no conclusion.

## 1. `frame_p05` re-run — **IDENTICAL**

(43.8, −86.4), re-run exactly. Every printed digit of the output position and
of both change-and-σ cells matches the frozen anchor.

| | Frozen `frame_p05.html` | Re-run `p05probe_p05_rerun.html` |
|---|---|---|
| Output latitude | `43.8000088707` | `43.8000088707` |
| Output longitude | `-86.4000119439` | `-86.4000119439` |
| Δlat ± σ | `0.03193″ ±0.000700″ \| (0.986 m ±0.0216 m)` | `0.03193″ ±0.000700″ \| (0.986 m ±0.0216 m)` |
| Δlon ± σ | `-0.04300″ ±0.000826″ \| (-0.961 m ±0.0185 m)` | `-0.04300″ ±0.000826″ \| (-0.961 m ±0.0185 m)` |

## 2. Session control — `frame_p04` re-run — **IDENTICAL**

(43.0, −84.5), the N0 point.

| | Frozen `frame_p04.html` | Re-run `p05probe_p04_control.html` |
|---|---|---|
| Output latitude | `43.0000084850` | `43.0000084850` |
| Output longitude | `-84.5000097815` | `-84.5000097815` |
| Δlat ± σ | `0.03055″ ±0.000657″ \| (0.943 m ±0.0203 m)` | `0.03055″ ±0.000657″ \| (0.943 m ±0.0203 m)` |
| Δlon ± σ | `-0.03521″ ±0.000658″ \| (-0.798 m ±0.0149 m)` | `-0.03521″ ±0.000658″ \| (-0.798 m ±0.0149 m)` |

## 3. The four neighbours, ±0.1° in each axis

Values exactly as beta NCAT printed them. `\|` separates the three renderings
NCAT puts in one cell (east-longitude DMS, west-longitude packed, negative-west
decimal).

### (43.700000, −86.400000) — `p05probe_p05_nbr_lat_lo.html`
```
Output latitude    N43° 42′ 00.02965″ | N434200.02965 | 43.7000082359
Output longitude   E273° 35′ 59.96157″ | W0862400.03843 | -86.4000106762
Delta lat  + sigma  0.02965″ ±0.000761″ | (0.915 m ±0.0235 m)
Delta lon  + sigma -0.03843″ ±0.000882″ | (-0.861 m ±0.0198 m)
```

### (43.900000, −86.400000) — `p05probe_p05_nbr_lat_hi.html`
```
Output latitude    N43° 54′ 00.03283″ | N435400.03283 | 43.9000091183
Output longitude   E273° 35′ 59.95686″ | W0862400.04314 | -86.4000119846
Delta lat  + sigma  0.03283″ ±0.001116″ | (1.013 m ±0.0344 m)
Delta lon  + sigma -0.04314″ ±0.001540″ | (-0.963 m ±0.0344 m)
```

### (43.800000, −86.500000) — `p05probe_p05_nbr_lon_lo.html`
```
Output latitude    N43° 48′ 00.03142″ | N434800.03142 | 43.8000087274
Output longitude   E273° 29′ 59.95835″ | W0863000.04165 | -86.5000115681
Delta lat  + sigma  0.03142″ ±0.001064″ | (0.970 m ±0.0328 m)
Delta lon  + sigma -0.04165″ ±0.001092″ | (-0.931 m ±0.0244 m)
```

### (43.800000, −86.300000) — `p05probe_p05_nbr_lon_hi.html`
```
Output latitude    N43° 48′ 00.03071″ | N434800.03071 | 43.8000085310
Output longitude   E273° 41′ 59.95884″ | W0861800.04116 | -86.3000114325
Delta lat  + sigma  0.03071″ ±0.000681″ | (0.948 m ±0.0210 m)
Delta lon  + sigma -0.04116″ ±0.000788″ | (-0.920 m ±0.0176 m)
```

### `frame_p05` itself, for the neighbours' centre
```
Output latitude    N43° 48′ 00.03193″ | N434800.03193 | 43.8000088707
Output longitude   E273° 35′ 59.95700″ | W0862400.04300 | -86.4000119439
Delta lat  + sigma  0.03193″ ±0.000700″ | (0.986 m ±0.0216 m)
Delta lon  + sigma -0.04300″ ±0.000826″ | (-0.961 m ±0.0185 m)
```

## Compact table

| Input lat | Input lon | Output lat | Output lon | σ lat (″) | σ lon (″) |
|---|---|---|---|---|---|
| 43.700000 | -86.400000 | 43.7000082359 | -86.4000106762 | 0.000761 | 0.000882 |
| **43.800000** | **-86.400000** | **43.8000088707** | **-86.4000119439** | **0.000700** | **0.000826** |
| 43.900000 | -86.400000 | 43.9000091183 | -86.4000119846 | 0.001116 | 0.001540 |
| 43.800000 | -86.500000 | 43.8000087274 | -86.5000115681 | 0.001064 | 0.001092 |
| 43.800000 | -86.300000 | 43.8000085310 | -86.3000114325 | 0.000681 | 0.000788 |
| 43.000000 | -84.500000 | 43.0000084850 | -84.5000097815 | 0.000657 | 0.000658 |

Every run reports `Input Epoch 2020.00` and `Output Epoch 2020.00`, the
contradiction already recorded at N0 §1.3 and CAPTURE.md §C.

## Files

New only. `anchors.json`, `raw/manifest.json` and every other existing file are
untouched. The coordinator asked for manifest entries "appended in the existing
pattern"; appending to `raw/manifest.json` would have modified an existing file,
so the entries are in a new manifest of the same shape.

| Path | What |
|---|---|
| `capture_p05_probe.py` | the probe, reproducible |
| `raw/p05_probe_manifest.json` | URL, POST fields (session tokens redacted), bytes, SHA-256, timestamp, per request |
| `raw/p05_probe_results.json` | the six extracted rows, machine-readable |
| `raw/p05probe_p05_rerun.html` | `96ad472e869e92c953f5a3bf81aa97e10466915e7b06961b76573117ec42b647` |
| `raw/p05probe_p05_nbr_lat_lo.html` | `058d3cf6a9ca325f8539cbbb24621a40cdaa120d1854928c1dbe6cb3cf79757f` |
| `raw/p05probe_p05_nbr_lat_hi.html` | `cfc6de93d5ef5dcf565a3b405168ba65de095f12d4147685af6e4a08b39997ca` |
| `raw/p05probe_p05_nbr_lon_lo.html` | `e3cad402df38574c7baafcac4004bf6bb818a7dce996f282d68116930e126776` |
| `raw/p05probe_p05_nbr_lon_hi.html` | `c9855634e987ef6f5c5a3361f7c043e4f178682966b13b1d824825f6cc14ae52` |
| `raw/p05probe_p04_control.html` | `084952414cc2ab96f4c7762eaa480f17b19959ae6d9622336848a510f40a78c4` |

The N0 digest caveat still applies: beta NCAT embeds a fresh `jsessionid` and
`ViewState` in every page, so these digests attest to the saved files and are
not reproducible by re-fetching. The **printed values** are what reproduced —
that is the finding in §1 and §2.

These captures inherit every limitation in CAPTURE.md's "What these anchors do
NOT prove", in particular: this is beta NCAT's implementation, not ground truth,
and the frame transformation behind it has no released official specification.
