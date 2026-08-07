"""The 12 fresh verification points, plus cross-zone pair points.

Chosen to avoid every latitude and longitude in the frozen anchor lattice
(tests/fixtures/ncat_anchors.py): anchor lats {45.3, 46.75, 48.15, 43.7, 44.8,
45.85, 41.75, 42.95, 44.15}, anchor lons {-90.1, -87.0, -83.6, -86.4,
-84.36666666666667, -83.1, -86.7, -82.5}. None below coincides with any of
those values.

Elevations are realistic Michigan orthometric heights in meters.
"""

# id, home zone, lat, lon (negative west), orthometric H (m), rationale
POINTS = [
    ("N1", "2111", 45.1050, -87.6050, 180.0,
     "Menominee - southern edge of the North zone band, west of the CM"),
    ("N2", "2111", 48.0500, -88.5500, 190.0,
     "Isle Royale - northern latitude extreme, far-west longitude"),
    ("N3", "2111", 46.4953, -84.3453, 183.0,
     "Sault Ste. Marie - realistic city where a survey job could sit, far east"),
    ("N4", "2111", 47.1211, -88.5694, 275.0,
     "Houghton - high latitude, Keweenaw, west of the CM"),
    ("C1", "2112", 43.6000, -86.4500, 200.0,
     "Silver Lake / Mears - southern edge of the Central band, west extreme"),
    ("C2", "2112", 45.9000, -84.7200, 190.0,
     "Brevort near the Straits - northern edge of the Central band; N/C pair point"),
    ("C3", "2112", 44.7631, -85.6206, 187.0,
     "Traverse City - realistic city where a survey job could sit"),
    ("C4", "2112", 44.3000, -83.5000, 181.0,
     "Tawas area - eastern longitude extreme of the Central zone"),
    ("S1", "2113", 41.9000, -86.5500, 220.0,
     "Niles/Buchanan - southern latitude extreme, west side"),
    ("S2", "2113", 44.2520, -85.4012, 397.0,
     "Cadillac - northern edge of the South band, high elevation; C/S pair point"),
    ("S3", "2113", 42.3314, -83.0458, 183.0,
     "Detroit - realistic city where a survey job could sit, east side"),
    ("S4", "2113", 42.7800, -86.0500, 190.0,
     "Holland area - west side, mid-band"),
]

# Cross-zone queries: (point id, extra zone). The point's lat/lon/H come from
# POINTS above; NS is its own probe point between the N and S bands.
NS_PROBE = ("NS", None, 44.6500, -85.5000, 310.0,
            "Kalkaska area - between the North and South bands; probes whether "
            "NCAT accepts a point in both 2111 and 2113 for the N<->S pair")

EXTRA_ZONE_QUERIES = [
    ("C2", "2111"),   # N<->C pair
    ("S2", "2112"),   # C<->S pair
    ("NS", "2111"),   # N<->S pair probe
    ("NS", "2113"),
]
