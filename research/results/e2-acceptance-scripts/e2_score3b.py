"""E2-B gate 3b's score (research/e2-acceptance.md 6.5): rang's tables
(R/rang-run/calibrate) against CASA's (R/casa/tables, e2_casa3b.py), class B
as the averaging validation's scorer (e2avg_luno.score, which ran on LUNO
scans 1-2 before the freeze) plus the secondary: Gsec and F per term, and
the composite of the tables applied to the secondary (K, B from the primary,
F from the secondary) on its rows.

    python e2_score3b.py R MS [--dev]     -> R/g3b.json

MS is any copy with the leg's rows (R/casa/e2b.ms). Sealed (6.7): it refuses
an E2 result directory until the amendment that names `calibrate.average_freq`
is in HEAD's research/e2-acceptance.md; `--dev` only for a development
directory (its path names `dryrun` or `dev`).
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2avg_common as C
from e2avg_luno import _first_unflagged
from rang import cal_apply

FCAL, XCAL, GCAL = "J1939-6342", "J1331+3030", "J1833-2103"


def amended():
    """True once HEAD's protocol lists the average_freq amendment in 6.7."""
    text = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:research/e2-acceptance.md"],
                          capture_output=True, text=True, check=True).stdout  # fmt: skip
    tail = text.split("- Amendments:", 1)[-1].split("\n## ", 1)[0]
    return "calibrate.average_freq" in tail


def guard(r, dev):
    if dev:
        if not any(k in str(r).lower() for k in ("dryrun", "dev")):
            raise SystemExit("--dev only for a development directory")
        return
    if not amended():
        raise SystemExit(
            "sealed (e2-acceptance.md 6.7): the average_freq amendment is not in HEAD"
        )


def scores(rdir, cdir, ms, secondary):
    names = ["K", "G", "B", "Gpol", "Kcross", "Xf", "Df"] + (
        ["Gsec", "F"] if secondary else []
    )
    r = {n: C.table(rdir / n) for n in names}
    c = {n: C.table(cdir / n) for n in names}
    out = {"terms": {}}
    out["terms"]["K"] = k = C.term_diff(r["K"], c["K"], "delay")
    k["class_b"] = bool(k["abs_ns"]["median"] <= 0.01 and k["abs_ns"]["p95"] <= 0.03)
    for n in ("G", "B") + (("Gsec", "F") if secondary else ()):
        out["terms"][n] = C.term_diff(r[n], c[n], "complex")
    g = out["terms"]["Gpol"] = C.term_diff(r["Gpol"], c["Gpol"], "phase")
    g["class_b"] = bool(g["abs_deg"]["median"] <= 0.1)
    pa, fa, pb, fb, _, _ = C.matched(r["Kcross"], c["Kcross"])
    ok = ~fa[:, 0, 0] & ~fb[:, 0, 0]
    kx = {"abs_ns": C.stats(np.abs(pa[ok, 0, 0].real - pb[ok, 0, 0].real))}
    kx["class_b"] = bool(kx["abs_ns"].get("max", 1.0) <= 0.02)
    out["terms"]["Kcross"] = kx
    xr, xc = _first_unflagged(r["Xf"]), _first_unflagged(c["Xf"])
    xd = np.degrees(np.abs(np.angle(xr / xc)))
    xf = {"abs_deg": C.stats(xd)}
    xf["class_b"] = bool(xf["abs_deg"]["median"] <= 0.5 and xf["abs_deg"]["p95"] <= 2.0)
    out["terms"]["Xf"] = xf
    pa, fa, pb, fb, _, _ = C.matched(r["Df"], c["Df"])
    diffs = []
    for p in range(pa.shape[0]):
        for q in range(pa.shape[0]):
            if p == q:
                continue
            for i, j in ((0, 1), (1, 0)):
                ok = ~fa[p, :, i] & ~fa[q, :, j] & ~fb[p, :, i] & ~fb[q, :, j]
                ga = pa[p, :, i] + np.conj(pa[q, :, j])
                gb = pb[p, :, i] + np.conj(pb[q, :, j])
                diffs.append(np.abs(ga - gb)[ok])
    df = {"abs": C.stats(np.concatenate(diffs)), "flags_differ": int((fa != fb).sum())}
    df["class_b"] = bool(df["abs"]["median"] <= 1e-3 and df["abs"]["p95"] <= 5e-3)
    out["terms"]["Df"] = df
    pooled = [cal_apply.POOLED] * 3
    fcal = C.field_id(ms, FCAL)
    a, fa = C.composite(ms, fcal, [r[n] for n in ("K", "G", "B")], pooled, step=8)
    b, fb = C.composite(ms, fcal, [c[n] for n in ("K", "G", "B")], pooled, step=8)
    out["composite_fcal_KGB"] = C.rel_stats(a, fa, b, fb)
    if secondary:
        gcal = C.field_id(ms, GCAL)
        tf = [fcal, gcal, fcal]
        a, fa = C.composite(ms, gcal, [r[n] for n in ("K", "F", "B")], tf, step=1)
        b, fb = C.composite(ms, gcal, [c[n] for n in ("K", "F", "B")], tf, step=1)
        out["composite_gcal_KFB"] = C.rel_stats(a, fa, b, fb)
    out["class_b_all"] = bool(
        all(v["class_b"] for k, v in out.items() if k.startswith("composite"))
        and all(v.get("class_b", True) for v in out["terms"].values())
    )
    return out


def main(argv):
    dev = "--dev" in argv
    r, ms = [Path(a) for a in argv if a != "--dev"][:2]
    guard(r, dev)
    rdir, cdir = r / "rang-run" / "calibrate", r / "casa" / "tables"
    out = scores(rdir, cdir, ms, secondary=(cdir / "F").exists())
    C.write(r / "g3b.json", out)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
