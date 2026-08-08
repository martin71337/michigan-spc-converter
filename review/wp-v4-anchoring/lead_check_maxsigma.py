import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lead_check_vertcon import ERR, TRN, biquad, frac, read_vertcon

trn = read_vertcon(TRN)
err = read_vertcon(ERR)
lat, lon = 43.05, -86.20
r, c = frac(trn, lat, lon)
print(f"43.05 N / 86.20 W -> row={r} col={c} (integral means an exact node)")

n = trn["values"][int(round(r)) * trn["nlon"] + int(round(c))]
s = err["values"][int(round(r)) * err["nlon"] + int(round(c))]
print(f"  .trn node value   {n:.6f} m")
print(f"  .err node value   {s:.6f} m")
print(f"  biquad-nearest    {biquad(trn, lat, lon, 'nearest'):.6f} m")
print(f"  biquad-floor      {biquad(trn, lat, lon, 'floor'):.6f} m")
print()
print("  plan 2.8 states   shift -0.1466 m, sigma 0.3656 m, 249% of the shift")
print(f"  measured          shift {n:.4f} m, sigma {s:.4f} m, "
      f"{abs(s / n) * 100:.0f}% of the shift")
print(f"  NCAT returned     shift -0.144 m, sigma 0.366 m (printed to 0.001)")
