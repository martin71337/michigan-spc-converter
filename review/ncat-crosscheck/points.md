# Verification points — NCAT live crosscheck, 2026-08-06

Twelve fresh points, four per zone, chosen to avoid every latitude and every
longitude in the frozen anchor lattice (`tests/fixtures/ncat_anchors.py`):
anchor latitudes {45.3, 46.75, 48.15, 43.7, 44.8, 45.85, 41.75, 42.95, 44.15}
and anchor longitudes {-90.1, -87.0, -83.6, -86.4, -84.36666666666667, -83.1,
-86.7, -82.5} appear nowhere below — different values, not just different
pairings.

Longitudes are signed, **negative west** — the convention selected for every
program run in this exercise. Elevations are realistic Michigan orthometric
heights in meters.

## Michigan North (2111), band roughly 45.0–48.4 N

| ID | Lat | Lon | H (m) | Rationale |
|----|-----|-----|-------|-----------|
| N1 | 45.1050 | -87.6050 | 180 | Menominee — southern edge of the North band, west of the central meridian |
| N2 | 48.0500 | -88.5500 | 190 | Isle Royale — northern latitude extreme, far-west longitude |
| N3 | 46.4953 | -84.3453 | 183 | Sault Ste. Marie — realistic city where a survey job could sit; far east |
| N4 | 47.1211 | -88.5694 | 275 | Houghton — high latitude, Keweenaw, west of the CM |

## Michigan Central (2112), band roughly 43.5–46.0 N

| ID | Lat | Lon | H (m) | Rationale |
|----|-----|-----|-------|-----------|
| C1 | 43.6000 | -86.4500 | 200 | Silver Lake / Mears — southern edge of the Central band, west extreme |
| C2 | 45.9000 | -84.7200 | 190 | Brevort near the Straits — northern band edge; the N↔C zone-pair point |
| C3 | 44.7631 | -85.6206 | 187 | Traverse City — realistic city where a survey job could sit |
| C4 | 44.3000 | -83.5000 | 181 | Tawas area — eastern longitude extreme |

## Michigan South (2113), band roughly 41.6–44.3 N

| ID | Lat | Lon | H (m) | Rationale |
|----|-----|-----|-------|-----------|
| S1 | 41.9000 | -86.5500 | 220 | Niles/Buchanan — southern latitude extreme, west side |
| S2 | 44.2520 | -85.4012 | 397 | Cadillac — northern band edge, highest test elevation; the C↔S zone-pair point |
| S3 | 42.3314 | -83.0458 | 183 | Detroit — realistic city where a survey job could sit; east side |
| S4 | 42.7800 | -86.0500 | 190 | Holland area — west side, mid-band |

## Extra point for the N↔S pair

| ID | Lat | Lon | H (m) | Rationale |
|----|-----|-----|-------|-----------|
| NS | 44.6500 | -85.5000 | 310 | Kalkaska area — sits between the North and South bands, since those bands do not overlap. NCAT **accepted** this point in both 2111 and 2113 (no refusal), so it serves as the N↔S pair point. In 2111 it produces a negative northing (-13,694.788 m), a useful stress input. |

## Zone-pair usage

| Directed pair | Point | Why |
|---|---|---|
| 2111↔2112 | C2 | inside both the North and Central bands, near the N/C boundary |
| 2112↔2113 | S2 | inside both the Central and South bands, near the C/S boundary |
| 2111↔2113 | NS | between the two non-adjacent bands; both zones' NCAT results exist |

No NCAT refusals occurred for any point in any queried zone; no replacements
were needed.
