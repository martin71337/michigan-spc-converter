"""Lead experiment: which composition reproduces the frozen NCAT frame anchors?

Candidates, all evaluated at the fixed epochs 2010.0 -> 2020.00:
  P1  HTDP composition (NAD83(2011) -> ITRF94 -> ITRF2020, params at 2010.0)
      then EPP2022 rotation over +10.0 yr, COORDINATE-FRAME sign (frit94's
      x2 = ds*x + rz*y - ry*z shape).
  P2  same, EPP with the OPPOSITE (position-vector) sign.
  P3  HTDP composition alone, no EPP step (NATRF2022 == ITRF2020@2010).
  P4  HTDP composition with params evaluated at 2020.0, then EPP CF +10y.
  P5  P1 but Helmert legs evaluated at 2020.0 and EPP over 0 yr (pure relabel).

Truth: review/nsrs-h1-anchors/anchors.json frame anchors (NCAT printed
lat/lon to 1e-10 deg). This is a scratchpad experiment, not production code.
"""
import json
import math

A = 6378137.0
F = 1.0 / 298.257222101  # HTDP's own GRS80 (htdp.f:151-163)
E2 = F * (2.0 - F)
RHOSEC = math.degrees(1.0) * 3600.0  # arcsec per radian


def geodetic_to_ecef(lat_deg, lon_deg, h):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    n = A / math.sqrt(1.0 - E2 * math.sin(lat) ** 2)
    x = (n + h) * math.cos(lat) * math.cos(lon)
    y = (n + h) * math.cos(lat) * math.sin(lon)
    z = (n * (1.0 - E2) + h) * math.sin(lat)
    return x, y, z


def ecef_to_geodetic(x, y, z):
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - E2))
    for _ in range(20):
        n = A / math.sqrt(1.0 - E2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat_new = math.atan2(z, p * (1.0 - E2 * n / (n + h)))
        if abs(lat_new - lat) < 1e-15:
            lat = lat_new
            break
        lat = lat_new
    n = A / math.sqrt(1.0 - E2 * math.sin(lat) ** 2)
    h = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), h


# HTDP /tranpa/ (IGS convention), ITRF94 -> frame, evaluated at date.
# (tx m, ty, tz, dtx, dty, dtz, rx arcsec, ry, rz, drx, dry, drz, scale, dscale, refepc)
NAD83 = (0.9910, -1.9072, -0.5129, 0.0, 0.0, 0.0,
         0.02579, 0.00965, 0.01166, 0.0000532, -0.0007423, -0.0000316,
         0.0, 0.0, 1997.0)
ITRF2020 = (-0.01290, 0.00241, 0.02827, -0.00079, 0.00070, 0.00124,
            -0.00029978, 0.00042037, 0.00031714,
            -0.00001347, 0.00001514, 0.00001973,
            0.05109e-9, 0.07201e-9, 2010.0)


def frit94(xyz, p, date):
    """ITRF94 -> frame p at date (htdp.f frit94, linearized)."""
    (tx, ty, tz, dtx, dty, dtz, rx, ry, rz, drx, dry, drz, sc, dsc, ref) = p
    dt = date - ref
    T = (tx + dtx * dt, ty + dty * dt, tz + dtz * dt)
    R = ((rx + drx * dt) / RHOSEC, (ry + dry * dt) / RHOSEC,
         (rz + drz * dt) / RHOSEC)
    ds = 1.0 + sc + dsc * dt
    x1, y1, z1 = xyz
    x2 = T[0] + ds * x1 + R[2] * y1 - R[1] * z1
    y2 = T[1] - R[2] * x1 + ds * y1 + R[0] * z1
    z2 = T[2] + R[1] * x1 - R[0] * y1 + ds * z1
    return x2, y2, z2


def toit94(xyz, p, date):
    """frame p -> ITRF94 at date (htdp.f toit94: negated params)."""
    (tx, ty, tz, dtx, dty, dtz, rx, ry, rz, drx, dry, drz, sc, dsc, ref) = p
    neg = (-tx, -ty, -tz, -dtx, -dty, -dtz, -rx, -ry, -rz, -drx, -dry, -drz,
           -sc, -dsc, ref)
    return frit94(xyz, neg, date)


# EPP2022 NA plate, mas/yr (frozen capture epp2022-beta-values.csv)
WX, WY, WZ = 0.046, -0.704, -0.047
MAS = 1.0 / 1000.0 / RHOSEC  # radians per mas


def epp_rotate(xyz, years, sign):
    """Apply the plate rotation over `years`, sign=+1 CF-shape, -1 PV-shape."""
    rx = sign * WX * years * MAS
    ry = sign * WY * years * MAS
    rz = sign * WZ * years * MAS
    x, y, z = xyz
    # frit94's shape: x2 = x + rz*y - ry*z etc.
    return (x + rz * y - ry * z,
            -rz * x + y + rx * z,
            ry * x - rx * y + z)


def run(anchors):
    print(f"{'anchor':>22} {'cand':>4} {'dLat_mas_err':>13} {'dLon_mas_err':>13}")
    sums = {}
    for a in anchors:
        lat_in = float(a["input_lat_dd"]) if "input_lat_dd" in a else float(a["input_lat"])
        lon_in = float(a["input_lon_dd"]) if "input_lon_dd" in a else float(a["input_lon"])
        lat_out = float(a["output_lat_dd"])
        lon_out = float(a["output_lon_dd"])
        xyz = geodetic_to_ecef(lat_in, lon_in, 0.0)
        candidates = {}
        it94_2010 = toit94(xyz, NAD83, 2010.0)
        itrf2020_2010 = frit94(it94_2010, ITRF2020, 2010.0)
        candidates["P1"] = epp_rotate(itrf2020_2010, 10.0, +1)
        candidates["P2"] = epp_rotate(itrf2020_2010, 10.0, -1)
        candidates["P3"] = itrf2020_2010
        it94_2020 = toit94(xyz, NAD83, 2020.0)
        itrf2020_2020 = frit94(it94_2020, ITRF2020, 2020.0)
        candidates["P4"] = epp_rotate(itrf2020_2020, 10.0, +1)
        candidates["P5"] = itrf2020_2020
        for name, out in candidates.items():
            la, lo, _h = ecef_to_geodetic(*out)
            dlat_mas = (la - lat_out) * 3600e3
            dlon_mas = (lo - lon_out) * 3600e3
            sums.setdefault(name, [0.0, 0])
            sums[name][0] += math.hypot(dlat_mas, dlon_mas * math.cos(math.radians(lat_in)))
            sums[name][1] += 1
            label = a.get("name", "?")
            print(f"{label:>22} {name:>4} {dlat_mas:13.3f} {dlon_mas:13.3f}")
    print("\nmean position error vs NCAT (mas; 1 mas ~ 31 mm lat):")
    for name, (tot, cnt) in sorted(sums.items()):
        print(f"  {name}: {tot / cnt:10.3f} mas ~ {tot / cnt * 30.9:8.1f} mm")


with open(r"C:\claude-projects\coord-convert\review\nsrs-h1-anchors\anchors.json",
          encoding="utf-8") as fh:
    data = json.load(fh)

frames = [a for a in data["frame_anchors"]
          if a.get("input_datum", "").startswith("NAD83")]
print(f"{len(frames)} forward frame anchors")
# normalize key names by peeking at the first record
k = frames[0].keys()
print("keys:", sorted(k))
run(frames)
