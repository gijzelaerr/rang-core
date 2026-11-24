# SPDX-License-Identifier: MIT
"""DD4 catalogue step (research/dd4-eso137.md, sections 3 and 4).

    python tools/oracles/dd4/catalogue.py CATDIR OUT.json

Reads the VizieR TSV files of RACS-low DR1 (Gaussian component tables
`gausscut`, `gaussreg`) and RACS-mid DR1 (`gcompsm`). It matches components
within 10″ and interpolates each flux to 1043.15 MHz in log-log between
887.5 and 1367.5 MHz (α = −0.7 when only RACS-low has the component). It
applies the Mauch et al. (2020) MeerKAT L-band beam, then selects the
facet directions by the frozen rule. The input files are third-party
data; they are parsed as numbers only.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

RA0, DEC0 = 243.80, -60.91  # degrees, the cone centre (the pilot's phase centre)
PHASE_DIR = (4.25503999, -1.06300733)  # radians, cal2.ms PHASE_DIR
NU, NU_LOW, NU_MID = 1043.15e6, 887.5e6, 1367.5e6
ALPHA_DEFAULT = -0.7
MATCH_ARCSEC = 10.0
THETA_B_ARCMIN = 57.5 * (1.5e9 / NU)
S_FACET = 0.050  # Jy apparent
S_MODEL = 0.005
R_MIN, R_MAX, SEP_MIN = 0.15, 1.0, 0.2  # degrees
NFACET = 4
HALF_IMAGE_DEG = 2880 * 3.0 / 3600 / 2


def tables(path):
    """{table name: list of row dicts} from a VizieR ASU-TSV file."""
    out, name, header, skip = {}, None, None, 0
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#Table"):
            name = line.split("\t")[1].rstrip(":").strip()
            out[name], header = [], None
            continue
        if not line.strip() or line.startswith("#") or name is None:
            continue
        if header is None:
            header = [h.strip() for h in line.split("\t")]
            skip = 2  # the unit line and the dashes
            continue
        if skip:
            skip -= 1
            continue
        out[name].append(
            dict(zip(header, (v.strip() for v in line.split("\t")), strict=False))
        )
    return out


def lm(ra, dec):
    """SIN direction cosines about PHASE_DIR (radians in, radians out)."""
    ra0, dec0 = PHASE_DIR
    da = ra - ra0
    l = math.cos(dec) * math.sin(da)
    m = math.sin(dec) * math.cos(dec0) - math.cos(dec) * math.sin(dec0) * math.cos(da)
    return l, m


def beam(rho_deg):
    """Mauch et al. 2020 cosine-squared power beam, rho in degrees."""
    x = 1.189 * (rho_deg * 60.0) / THETA_B_ARCMIN
    denom = 1.0 - 4.0 * x * x
    if abs(denom) < 1e-12:
        return (math.pi / 4) ** 2
    return (math.cos(math.pi * x) / denom) ** 2


def components(catdir):
    low = tables(Path(catdir) / "racs-low.tsv")
    mid = tables(Path(catdir) / "racs-mid.tsv")
    lows = [r for t in low if t.endswith(("gausscut", "gaussreg")) for r in low[t]]
    mids = [r for t in mid if t.endswith("gcompsm") for r in mid[t]]
    mid_pos = np.array([[float(r["RAJ2000"]), float(r["DEJ2000"])] for r in mids])
    mid_flux = np.array([float(r["Ftot"]) for r in mids]) / 1e3
    out = []
    for r in lows:
        ra, dec, s888 = (
            float(r["RAJ2000"]),
            float(r["DEJ2000"]),
            float(r["Fgauss"]) / 1e3,
        )
        if not s888 > 0:
            continue
        d = (
            np.hypot(
                (mid_pos[:, 0] - ra) * math.cos(math.radians(dec)), mid_pos[:, 1] - dec
            )
            * 3600
        )
        k = int(np.argmin(d)) if len(d) else -1
        if k >= 0 and d[k] <= MATCH_ARCSEC and mid_flux[k] > 0:
            alpha = math.log(mid_flux[k] / s888) / math.log(NU_MID / NU_LOW)
            matched = True
        else:
            alpha, matched = ALPHA_DEFAULT, False
        s_nu = s888 * (NU / NU_LOW) ** alpha
        l, m = lm(math.radians(ra), math.radians(dec))
        rho = math.degrees(math.hypot(l, m))
        out.append({
            "id": r.get("GID", ""), "ra_deg": ra, "dec_deg": dec, "l": l, "m": m,
            "rho_deg": rho, "s888": s888, "alpha": alpha, "matched": matched,
            "s1043": s_nu, "s_app": s_nu * beam(rho),
        })  # fmt: skip
    return out


def select(comps):
    inside = [
        c
        for c in comps
        if max(abs(math.degrees(c["l"])), abs(math.degrees(c["m"]))) < HALF_IMAGE_DEG
    ]
    cands = sorted(
        (c for c in inside if R_MIN <= c["rho_deg"] <= R_MAX and c["s_app"] >= S_FACET),
        key=lambda c: -c["s_app"],
    )
    chosen = []
    for c in cands:
        ok = (
            all(
                math.degrees(math.hypot(c["l"] - o["l"], c["m"] - o["m"])) >= SEP_MIN
                for o in chosen
            )
            and c["rho_deg"] >= SEP_MIN
        )
        if ok:
            chosen.append(c)
        if len(chosen) == NFACET:
            break
    return inside, chosen


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    comps = components(argv[0])
    inside, chosen = select(comps)
    model = [c for c in inside if c["s_app"] >= S_MODEL]
    rec = {
        "note": "research/dd4-eso137.md sections 3-4",
        "theta_b_arcmin": THETA_B_ARCMIN,
        "n_low_components": len(comps),
        "n_inside": len(inside),
        "n_matched": sum(c["matched"] for c in comps),
        "directions": [{"l": 0.0, "m": 0.0, "name": "d0"}]
        + [
            {"l": c["l"], "m": c["m"], "name": f"d{k + 1}", **c}
            for k, c in enumerate(chosen)
        ],
        "model_components": model,
    }
    Path(argv[1]).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(
        json.dumps(
            {
                k: rec[k]
                for k in ("theta_b_arcmin", "n_low_components", "n_inside", "n_matched")
            }
        )
    )
    for c in chosen:
        print(f"{c['id']} rho {c['rho_deg']:.3f} deg  S888 {c['s888']:.3f}  alpha {c['alpha']:.2f}  "
              f"S1043 {c['s1043']:.3f}  B {c['s_app'] / c['s1043']:.3f}  Sapp {c['s_app']:.3f} Jy")  # fmt: skip
    print(
        "model components >= 5 mJy:",
        len(model),
        "total Sapp",
        round(sum(c["s_app"] for c in model), 3),
    )


if __name__ == "__main__":
    main()
