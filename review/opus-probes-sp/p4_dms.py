"""Probe 4: hammer latitude_dms / longitude_dms for carry, rounding and sign."""
import sys, random, re
sys.path.insert(0, r"C:\claude-projects\coord-convert")
from michspc.fileio import formatting as fmt

PAT = re.compile(r"^(\d{2,})°(\d{2})'(\d{2}\.\d{5})\"([NSEW])$")

bad = []


def check(v, f, letters):
    s = f(v)
    m = PAT.match(s)
    if not m:
        bad.append(("shape", v, s)); return
    d, mm, ss, h = int(m.group(1)), int(m.group(2)), float(m.group(3)), m.group(4)
    if mm >= 60:
        bad.append(("minute>=60", v, s))
    if ss >= 60.0:
        bad.append(("second>=60", v, s))
    if h not in letters:
        bad.append(("letter", v, s))
    # Does the DMS reconstruct the value?
    back = d + mm / 60.0 + ss / 3600.0
    if abs(back - abs(v)) > 2e-9:
        bad.append(("magnitude", v, s, back, abs(v)))
    # Hemisphere must follow the SIGN of the stored value.
    want = letters[0] if v < 0 else letters[1]
    if h != want:
        bad.append(("hemisphere", v, s, want))


LAT = ("S", "N")
LON = ("W", "E")

# Boundary-engineered values: exactly on 5-dp second ticks and nudged.
targets = []
for base_sec in (0.0, 59.999995, 59.9999949999, 59.99999500001,
                 3599.999995, 3599.9999949, 3599.99999500001,
                 59.999999999, 3599.999999999, 1.0, 60.0, 3600.0):
    targets.append(base_sec / 3600.0)
targets += [0.0, -0.0, 180.0, -180.0, 90.0, -90.0, 1e-12, -1e-12,
            42.7325, -84.5555, 45.99999999999, -179.99999999999]

for t in targets:
    check(t, fmt.latitude_dms, LAT)
    check(t, fmt.longitude_dms, LON)

# Dense sweeps
step = 1e-7
v = 41.0
while v < 48.5:
    check(v, fmt.latitude_dms, LAT)
    v += 1e-5
v = -90.5
while v < -82.0:
    check(v, fmt.longitude_dms, LON)
    v += 1e-5

# Every 1e-5 arcsecond tick around each arcsecond boundary in Michigan's range
for deg in range(41, 49):
    for sec_tick in range(0, 3600 * 1, 1):  # each arcsecond of the first minute
        for eps in (-1e-11, 0.0, 1e-11, -5e-6 / 3600, 5e-6 / 3600):
            val = deg + (sec_tick + 0.9999995) / 3600.0 + eps
            check(val, fmt.latitude_dms, LAT)

rnd = random.Random(20260807)
for _ in range(400000):
    check(rnd.uniform(-180, 180), fmt.longitude_dms, LON)
    check(rnd.uniform(-90, 90), fmt.latitude_dms, LAT)

print("failures:", len(bad))
for b in bad[:25]:
    print(b)

# Explicit named boundary answers for the report
for v in (0.0, -0.0, 180.0, -180.0, -1e-12, 1e-12):
    print(f"lat_dms({v!r:>8}) = {fmt.latitude_dms(v)!r:<22} "
          f"lat({v!r}) = {fmt.latitude(v)!r}")
for v in (0.0, -0.0, 180.0, -180.0, -1e-12):
    print(f"lon_dms({v!r:>8}) = {fmt.longitude_dms(v)!r:<22} "
          f"lon({v!r}) = {fmt.longitude(v)!r}")
print("angle_dms default decimals check:", fmt.angle_dms(-0.25), fmt.angle_dms(42.7325))
