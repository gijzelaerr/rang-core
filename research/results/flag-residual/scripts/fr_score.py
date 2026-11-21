"""flag-residual (#51), research/flag-residual.md section 5: gates G-S, G-F, G-D.

    python fr_score.py RUN_ROOT OUT.json

E2-N (arms off and on, RUN_ROOT/e2n-{off,on}.ms and their run directories):
- G-S: flagged fraction of every solved table's solutions; per calibrator field, each
  antenna's unflagged cells on its baseline to the reference antenna after the run
  (antennas with none are counted); the on arm's residual.json (tripwire).
- G-F: J1744-5144's fluxscale (F step); 3C 286 (J1331+3030) p and chi, J1939-6342's
  residual polarisation, from CORRECTED_DATA averaged over rows per 64-channel block
  (linear feeds, parallactic angle applied: I = (XX+YY)/2, Q = (XX-YY)/2,
  U = (XY+YX)/2), medians over blocks.
- G-D: per calibrator field, S = sum w^2 |d|^2 / (sum w)^2 over cells unflagged in that arm
  (d: Stokes V consecutive-dump differences of the arm's CORRECTED_DATA, w: V's weight
  from WEIGHT_SPECTRUM); reported as sqrt(S_on / S_off).
A1 (RUN_ROOT/a1/a1-{off,on}.ms, generator output RUN_ROOT/a1/gen): on the calibrator fields
(0, 1, 2), cross baselines: fraction flagged of the truth's above_5sigma cells (recall) and of
cells clean in the truth's `any` mask (false flags), after each arm's run; B amplitude shape
error against truth (|B| / |B_true| per antenna and hand, divided by its median over channels;
median of |ratio - 1| over antennas, hands and channels).
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

from rang import core_ms, flag_residual
from rang.formats import caltable

CAL_FIELDS = ("J1939-6342", "J1744-5144", "J1331+3030")
XY, YX = 1, 2
BLOCK = 64


def field_ids(ms):
    with core_ms.open_table(f"{ms}/FIELD") as t:
        return {str(n): i for i, n in enumerate(t.getcol("NAME"))}


def summary(ms):
    return json.loads(
        (Path(f"{ms}.rang-run") / "calibrate" / "summary.json").read_text()
    )


def stokes(ms, fid):
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        cross = rows[a1 != a2]
        acc = None
        cnt = None
        for i in range(0, len(cross), 20000):
            r = cross[i : i + 20000]
            d = t.getcol_rows("CORRECTED_DATA", r)
            f = t.getcol_rows("FLAG", r)
            d = np.where(f, 0, d)
            s = d.sum(0)
            n = (~f).sum(0)
            acc = s if acc is None else acc + s
            cnt = n if cnt is None else cnt + n
    v = acc / np.maximum(cnt, 1)
    nb = v.shape[0] // BLOCK
    v = v[: nb * BLOCK].reshape(nb, BLOCK, 4).mean(1)
    i_, q_ = (v[:, 0] + v[:, 3]).real / 2, (v[:, 0] - v[:, 3]).real / 2
    u_ = (v[:, 1] + v[:, 2]).real / 2
    p = np.sqrt(q_**2 + u_**2) / i_
    chi = 0.5 * np.degrees(np.arctan2(u_, q_))
    return {"p_median": float(np.nanmedian(p)), "chi_median_deg": float(np.nanmedian(chi)),
            "i_median": float(np.nanmedian(i_))}  # fmt: skip


def refant_connectivity(ms, fid, refant):
    with core_ms.open_table(f"{ms}/ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
    ref = names.index(refant)
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        sel = rows[(a1 != a2) & ((a1 == ref) | (a2 == ref))]
        b1, b2 = t.getcol_rows("ANTENNA1", sel), t.getcol_rows("ANTENNA2", sel)
        good = np.zeros(len(names))
        for i in range(0, len(sel), 20000):
            f = t.getcol_rows("FLAG", sel[i : i + 20000])
            other = np.where(
                b1[i : i + 20000] == ref, b2[i : i + 20000], b1[i : i + 20000]
            )
            np.add.at(good, other, (~f.any(-1)).sum(1))
    good[ref] = np.nan
    return {
        "antennas_without": int(np.sum(good == 0)),
        "min_unflagged_cells": float(np.nanmin(good)),
    }


def implied_noise(ms, fid):
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        rows = rows[a1 != a2]
        a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        tm = t.getcol_rows("TIME", rows)
        sw = sw2d = 0.0
        times = np.unique(tm)
        for k in range(0, len(times) - 1, 2):
            ra, rb = rows[tm == times[k]], rows[tm == times[k + 1]]
            ka = a1[tm == times[k]].astype(np.int64) * 1000 + a2[tm == times[k]]
            kb = a1[tm == times[k + 1]].astype(np.int64) * 1000 + a2[tm == times[k + 1]]
            _, ia, ib = np.intersect1d(ka, kb, return_indices=True)
            if not len(ia):
                continue
            da, db = (
                t.getcol_rows("CORRECTED_DATA", ra[ia]),
                t.getcol_rows("CORRECTED_DATA", rb[ib]),
            )
            fa, fb = t.getcol_rows("FLAG", ra[ia]), t.getcol_rows("FLAG", rb[ib])
            wa = t.getcol_rows("WEIGHT_SPECTRUM", ra[ia]).astype(np.float64)
            va, vb = (da[..., XY] - da[..., YX]) / 2j, (db[..., XY] - db[..., YX]) / 2j
            ok = ~(fa[..., XY] | fa[..., YX] | fb[..., XY] | fb[..., YX])
            with np.errstate(divide="ignore", invalid="ignore"):
                w = 4.0 / (1.0 / wa[..., XY] + 1.0 / wa[..., YX])
            ok &= np.isfinite(w) & (w > 0)
            d2 = np.abs(va - vb) ** 2 / 2.0
            sw += float(w[ok].sum())
            sw2d += float((w[ok] ** 2 * d2[ok]).sum())
    return sw2d / sw**2 if sw > 0 else math.nan


def e2n(root):
    out = {}
    for arm in ("off", "on"):
        ms = root / f"e2n-{arm}.ms"
        if not Path(f"{ms}.rang-run/calibrate/summary.json").is_file():
            out[arm] = {"missing": True}
            continue
        s = summary(ms)
        ids = field_ids(ms)
        refant = (s.get("refant_auto") or {}).get("names", [None])[0]
        rec = {
            "solutions_flagged": flag_residual.solution_flag_fractions(s["steps"]),
            "fluxscale": next(
                (st.get("fluxscale") for st in s["steps"] if st["type"] == "F"), None
            ),
            "refant": refant,
            "connectivity": {
                f: refant_connectivity(ms, ids[f], refant) for f in CAL_FIELDS if refant
            },
            "pol_3c286": stokes(ms, ids["J1331+3030"]),
            "pol_1934": stokes(ms, ids["J1939-6342"]),
            "S": {f: implied_noise(ms, ids[f]) for f in CAL_FIELDS},
        }
        res = Path(f"{ms}.rang-run/calibrate/residual.json")
        if res.is_file():
            r = json.loads(res.read_text())
            rec["residual"] = {
                k: r[k]
                for k in (
                    "solutions_flagged_before",
                    "solutions_flagged_after",
                    "tripwire_fired",
                )
            }
            rec["residual_blocks"] = r["blocks"]
        out[arm] = rec
    if not out["off"].get("missing") and not out["on"].get("missing"):
        out["noise_ratio_on_over_off"] = {
            f: math.sqrt(out["on"]["S"][f] / out["off"]["S"][f]) for f in CAL_FIELDS
        }
    return out


def a1(root):
    gen = root / "a1" / "gen"
    if not (gen / "truth.npz").is_file():
        return {"missing": True}
    m = np.load(gen / "a1-full.rfi_mask.npz")
    z = np.load(gen / "truth.npz")
    out = {}
    for arm in ("off", "on"):
        ms = root / "a1" / f"a1-{arm}.ms"
        if not Path(f"{ms}.rang-run/calibrate/summary.json").is_file():
            out[arm] = {"missing": True}
            continue
        with core_ms.open_table(ms) as t:
            fid = t.getcol("FIELD_ID")
            a1_, a2_ = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
            nchan = int(m["nchan"])
            hit5 = n5 = hitc = nc = 0
            for i in range(0, t.nrows, 20000):
                sl = slice(i, min(i + 20000, t.nrows))
                sel = (fid[sl] <= 2) & (a1_[sl] != a2_[sl])
                f = t.getcol("FLAG", i, sl.stop - i).any(-1)
                any_ = np.unpackbits(m["any"][sl], axis=1, count=nchan).astype(bool)
                a5 = np.unpackbits(m["above_5sigma"][sl], axis=1, count=nchan).astype(
                    bool
                )
                f, any_, a5 = f[sel], any_[sel], a5[sel]
                hit5 += int((f & a5).sum())
                n5 += int(a5.sum())
                hitc += int((f & ~any_).sum())
                nc += int((~any_).sum())
        s = summary(ms)
        bpath = next(st["path"] for st in s["steps"] if st["type"] == "B")
        btab = caltable.read(bpath)
        b = np.abs(btab.params)  # (row, chan, par)
        ant = np.asarray(btab.main["ANTENNA1"])
        truth = np.abs(z["gauge0_bandpass"])  # (ant, chan, hand)
        errs = []
        for r in range(b.shape[0]):
            for h in range(min(2, b.shape[2])):
                ratio = b[r, :, h] / truth[ant[r], :, h]
                ratio = ratio / np.nanmedian(ratio)
                errs.append(np.abs(ratio - 1))
        out[arm] = {
            "recall_above_5sigma": hit5 / max(n5, 1),
            "false_flag_clean": hitc / max(nc, 1),
            "b_shape_error_median": float(np.nanmedian(np.concatenate(errs))),
        }
    return out


def main(root, outp):
    root = Path(root)
    res = {"e2n": e2n(root), "a1": a1(root)}
    Path(outp).write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main(*sys.argv[1:3])
