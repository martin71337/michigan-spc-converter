"""NGS HTDP v3.6.0 TRFPOS output for work package W3's end-to-end pins, frozen.

GENERATED - do not edit by hand. ``review/wgs84-w3/make_w3_anchors.py``
writes this file from ``review/wgs84-w3/w3_truth.json`` and reproduces it byte
for byte; ``tests/test_job_wgs84.py`` re-runs the generator and requires that.
The generator's docstring says why these records and no others.

Provenance (``w3_truth.json`` -> ``provenance``):

    tool       NGS HTDP v3.6.0 (htdp.f:27-28 'April 7, 2025')
    repository https://github.com/noaa-ngs/HTDP
    commit     59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c
    compiler   GNU Fortran (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
    build      gfortran -O0 -std=legacy -w *.f -o htdp_linux (x86_64, SSE2 double arithmetic)
    binary     sha256 3738c50c66901c02b751d391b8ca6a0c5eac667fbc7c30875c21b59f82f77f8f (W0's build, checked at capture)
    captured   2026-10-20T19:58:04+00:00
    truth file sha256 94b3a96f655da418658d097a37ad8739049bf93ddc6a678a9d6ce65415ef5fc3
    input      review/gate-wgs84-1/output.md, finding L5

    source SHA-256, the files committed unmodified at review/wgs84-w0/htdp-v3.6.0/:
    htdp.f    97a46675b4fb9de24152ed70fc3a34f72017e90cb77e4994696dfd5dffb75271
    initbd.f  66da175e3cb7a979b3179633a2517b194f14286e47f154bffca9760315de696d
    initeq.f  c2d92dec9d9c3402589c8a9d9aa873ddaefb2925577b38be252475c71cd0eac9
    initps.f  543eb7c650f8f9a8047bbf66e8cdddd205c32512ee46e069a0765e0b97655945
    initvl.f  06455583630018c888db5f6828e55972b80477548df92790a3e5a30483dc1e56

Calendar entry on both sides, the NAD 83 side always 1 1 2010; the exact stdin
of each run is stored with it. Inputs and outputs are HTDP's own strings,
longitude POSITIVE WEST, output ``2f16.10,f10.3`` (htdp.f:3293) with leading
blanks stripped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class W3Record:
    """One TRFPOS record between NAD 83(2011) at 2010.0 and a frame at ``observation_date``."""

    run_id: str
    frame_code: str
    frame_in_menu: int
    frame_out_menu: int
    observation_date: date
    stdin: str
    raw_sha256: str
    lat_in: str
    lonw_in: str
    h_in: str
    lat_out: str
    lonw_out: str
    h_out: str


L5_RECORDS: tuple[W3Record, ...] = (
    W3Record(
        run_id="l5_f10_2025-06-15",
        frame_code="WGS84(G1762)",
        frame_in_menu=10,
        frame_out_menu=1,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n10\n1\n1\n6 15 2025\n1\n1 1 2010\n3\nin.txt\n0\n0\n",
        raw_sha256="00744679fe2c3bf3680992951a9216b52a3014e43fac2395eb9d7d43c90fec97",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="42.9999914444",
        lonw_out="84.4999892422",
        h_out="166.096",
    ),
    W3Record(
        run_id="l5_f11_2025-06-15",
        frame_code="WGS84(G2139)",
        frame_in_menu=11,
        frame_out_menu=1,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n11\n1\n1\n6 15 2025\n1\n1 1 2010\n3\nin.txt\n0\n0\n",
        raw_sha256="70e13d807af024e62aaf1c9850f4f6eafb64a486fadf75259c77361116210697",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="42.9999914606",
        lonw_out="84.4999892204",
        h_out="166.098",
    ),
    W3Record(
        run_id="l5_f12_2025-06-15",
        frame_code="WGS84(G2296)",
        frame_in_menu=12,
        frame_out_menu=1,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n12\n1\n1\n6 15 2025\n1\n1 1 2010\n3\nin.txt\n0\n0\n",
        raw_sha256="784f213e139038a5e4819a7277387dcd13ca4b8cafcad09da308fc7fa4e62bdf",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="42.9999914726",
        lonw_out="84.4999892398",
        h_out="166.099",
    ),
    W3Record(
        run_id="l5_f25_2025-06-15",
        frame_code="ITRF2014",
        frame_in_menu=25,
        frame_out_menu=1,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n25\n1\n1\n6 15 2025\n1\n1 1 2010\n3\nin.txt\n0\n0\n",
        raw_sha256="ca0a6839f0195c6b05731c64a00542e60956e4992fecab906a3244d319a9a988",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="42.9999914597",
        lonw_out="84.4999892204",
        h_out="166.098",
    ),
    W3Record(
        run_id="l5_f26_2025-06-15",
        frame_code="ITRF2020",
        frame_in_menu=26,
        frame_out_menu=1,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n26\n1\n1\n6 15 2025\n1\n1 1 2010\n3\nin.txt\n0\n0\n",
        raw_sha256="b7809b95dd9bb863a35895e6e1f3982ad49b30016e6882bf0dc6adb0be748ea8",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="42.9999914716",
        lonw_out="84.4999892398",
        h_out="166.099",
    ),
)
"""Interim gate 1's L5 input, 43.0 N 84.5 W h 165.000 m, in each of the five
frames, to NAD 83(2011) at 2010.0."""

L5_REVERSE_RECORDS: tuple[W3Record, ...] = (
    W3Record(
        run_id="l5r_f10_2025-06-15",
        frame_code="WGS84(G1762)",
        frame_in_menu=1,
        frame_out_menu=10,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n1\n10\n1\n1 1 2010\n1\n6 15 2025\n3\nin.txt\n0\n0\n",
        raw_sha256="c1d668480d61cb58339050dfabf0beee9767f79671fe40d7b31fd3d53f60b88f",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="43.0000085556",
        lonw_out="84.5000107580",
        h_out="163.904",
    ),
    W3Record(
        run_id="l5r_f11_2025-06-15",
        frame_code="WGS84(G2139)",
        frame_in_menu=1,
        frame_out_menu=11,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n1\n11\n1\n1 1 2010\n1\n6 15 2025\n3\nin.txt\n0\n0\n",
        raw_sha256="2aee9039785b81a848f63cf69a6d91a261fafdaa494256bc947a844b59348db6",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="43.0000085394",
        lonw_out="84.5000107797",
        h_out="163.902",
    ),
    W3Record(
        run_id="l5r_f12_2025-06-15",
        frame_code="WGS84(G2296)",
        frame_in_menu=1,
        frame_out_menu=12,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n1\n12\n1\n1 1 2010\n1\n6 15 2025\n3\nin.txt\n0\n0\n",
        raw_sha256="01fc9b048584ebfe03eec24067276a7a841e9f77b7583eddd6aeedb824085008",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="43.0000085274",
        lonw_out="84.5000107604",
        h_out="163.901",
    ),
    W3Record(
        run_id="l5r_f25_2025-06-15",
        frame_code="ITRF2014",
        frame_in_menu=1,
        frame_out_menu=25,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n1\n25\n1\n1 1 2010\n1\n6 15 2025\n3\nin.txt\n0\n0\n",
        raw_sha256="c8aa538ae33279af695dc4c27e4d9bfac41199fd54b086ee254bb9ed9264d532",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="43.0000085404",
        lonw_out="84.5000107797",
        h_out="163.902",
    ),
    W3Record(
        run_id="l5r_f26_2025-06-15",
        frame_code="ITRF2020",
        frame_in_menu=1,
        frame_out_menu=26,
        observation_date=date(2025, 6, 15),
        stdin="4\nout.txt\n1\n26\n1\n1 1 2010\n1\n6 15 2025\n3\nin.txt\n0\n0\n",
        raw_sha256="7020bc8e23f968a30cc6a3b97f9d2ffcd9a2b06b78a9cf8d9c7dd7bc33b866e5",
        lat_in="43.0",
        lonw_in="84.5",
        h_in="165.000",
        lat_out="43.0000085284",
        lonw_out="84.5000107604",
        h_out="163.901",
    ),
)
"""The same numbers as a NAD 83(2011) position at 2010.0, to each of the five
frames at the same observation date."""
