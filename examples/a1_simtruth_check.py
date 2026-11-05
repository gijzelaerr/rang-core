"""Task A1: the host-side checks of the simulated truth (research/a1-simtruth.md, section 5).

Usage (host, worktree venv):
    python examples/a1_simtruth_check.py roundtrip VDIR EXPORT.npz TWIN.ms OUT.json [--parang]
    python examples/a1_simtruth_check.py noise VDIR MS TWIN.ms OUT.json

`roundtrip` compares CASA's CORRECTED_DATA (exported by
`examples/a1_simtruth_casa.py apply`) with P M P^T (parang False) or M
(parang True) computed in float64 from the sky model and the saved angles
(check 1, 2). `noise` reads DATA of the MS and of its noiseless twin on the
twin's rows, measures sigma outside the RFI mask (check 4) and recomputes
DATA from the truth and seeds (check 5).
"""

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
from rang import core_ms
from rang import simtruth as st

EPS32 = 2.0**-23


def load(vdir):
    vdir = Path(vdir)
    meta = json.loads((vdir / "truth.json").read_text(encoding="utf-8"))
    d = st.design(meta["design"]["name"])
    t = np.load(vdir / "truth.npz")
    truth = {k[4:]: t[k] for k in t.files if k.startswith("raw_")}
    return d, meta, t, truth


def class_c(got, ref):
    """Check 1's per-element bound; returns the worst ratio |diff| / bound."""
    scale = np.abs(ref).max(axis=-1, keepdims=True)
    bound = np.maximum(1e-6 * np.abs(ref), 11 * EPS32 * scale)
    bound = np.where(bound > 0, bound, np.finfo(float).tiny)
    return np.abs(got - ref) / bound


def read_rows(ms, column, start, n):
    with core_ms.open_table(ms) as tab:
        return tab.getcol(column, start, n)


def roundtrip(args):
    started = time.perf_counter()
    d, meta, t, _ = load(args.vdir)
    ex = np.load(args.export)
    times = t["time"]
    tix = np.searchsorted(times, ex["TIME"] - 1e-3)
    if np.abs(times[tix] - ex["TIME"]).max() > 1e-3:
        raise SystemExit("export rows do not map to truth integrations")
    rows = st.Rows(
        tix.astype(np.int64),
        ex["ANTENNA1"].astype(np.int64),
        ex["ANTENNA2"].astype(np.int64),
    )
    sky = meta["target_components"]
    cal = t["calibrator_stokes"]
    q = t["parallactic_angle"]
    fields = t["field"]
    out = {
        "export": str(args.export),
        "parang": args.parang,
        "nrow": len(tix),
        "nchan": d.nchan,
    }
    worst = 0.0
    worst_at = None
    nfail = 0
    nelem = 0
    flags_equal = True
    data_equal = True
    per_field = {}
    delta_x = []
    casa_frame = {"elements": 0, "fail": 0, "worst_ratio": 0.0}
    chunk = 20000
    nrow = len(tix)
    for s in range(0, nrow, chunk):
        e = min(nrow, s + chunk)
        r = st.Rows(rows.tindex[s:e], rows.a1[s:e], rows.a2[s:e])
        m, _ = st.sky_coherency(d, r, t["uvw_antenna"], fields, sky, cal)
        if args.parang:
            ref = m
        else:
            ap = q[r.tindex, r.a1] + st.RECEPTOR_ANGLE
            aq = q[r.tindex, r.a2] + st.RECEPTOR_ANGLE
            ref = st.rotate(m, ap, aq)
        got = ex["CORRECTED_DATA"][s:e].astype(np.complex128)
        if args.parang and "parallactic_angle_casa_frame" in t.files:
            # Added measure (7.1, after check 2): CASA's output against the
            # truth de-rotated with the angle in CASA's measured frame.
            qc = t["parallactic_angle_casa_frame"]
            ap = q[r.tindex, r.a1] + st.RECEPTOR_ANGLE
            aq = q[r.tindex, r.a2] + st.RECEPTOR_ANGLE
            cp = qc[r.tindex, r.a1] + st.RECEPTOR_ANGLE
            cq = qc[r.tindex, r.a2] + st.RECEPTOR_ANGLE
            exp_casa = st.rotate(st.rotate(m, ap, aq), cp, cq, inverse=True)
            rc = class_c(got, exp_casa)
            casa_frame["elements"] += int(rc.size)
            casa_frame["fail"] += int((rc > 1).sum())
            casa_frame["worst_ratio"] = max(casa_frame["worst_ratio"], float(rc.max()))
        ratio = class_c(got, ref)
        rf = fields[r.tindex]
        for f in np.unique(rf):
            sel = rf == f
            name = st.FIELDS[f][0]
            rec = per_field.setdefault(
                name,
                {
                    "elements": 0,
                    "fail": 0,
                    "worst_ratio": 0.0,
                    "max_rel_to_cell_max": 0.0,
                },
            )
            rr = ratio[sel]
            rec["elements"] += int(rr.size)
            rec["fail"] += int((rr > 1).sum())
            rec["worst_ratio"] = max(rec["worst_ratio"], float(rr.max()))
            scale = np.abs(ref[sel]).max(-1, keepdims=True)
            rec["max_rel_to_cell_max"] = max(
                rec["max_rel_to_cell_max"],
                float((np.abs(got[sel] - ref[sel]) / scale).max()),
            )
        if args.parang:
            # Implied angle error on the polarised calibrator, from the cross hands:
            # in the sky frame XY + YX = 2U, XX - YY = 2Q.
            sel = rf == 1
            if sel.any():
                pol_ref = 0.5 * (ref[sel, :, 0] - ref[sel, :, 3]) + 0.5j * (
                    ref[sel, :, 1] + ref[sel, :, 2]
                )
                pol_got = 0.5 * (got[sel, :, 0] - got[sel, :, 3]) + 0.5j * (
                    got[sel, :, 1] + got[sel, :, 2]
                )
                delta_x.append(
                    np.abs(pol_got - pol_ref).ravel() / (2 * np.abs(pol_ref).ravel())
                )
        k = np.unravel_index(np.argmax(ratio), ratio.shape)
        if ratio[k] > worst:
            worst = float(ratio[k])
            worst_at = {
                "row": int(s + k[0]),
                "chan": int(k[1]),
                "corr": st.CORR[k[2]],
                "field": st.FIELDS[int(rf[k[0]])][0],
                "got": str(got[k]),
                "ref": str(ref[k]),
            }
        nfail += int((ratio > 1).sum())
        nelem += int(ratio.size)
        flags_equal &= not bool(ex["FLAG"][s:e].any())
        twin = read_rows(args.twin, "DATA", s, e - s)
        data_equal &= bool(np.array_equal(twin, ex["DATA"][s:e]))
    out.update(
        elements=nelem,
        fail=nfail,
        worst_ratio=worst,
        worst_at=worst_at,
        flags_equal_input=flags_equal,
        data_unchanged=data_equal,
        per_field=per_field,
    )
    if delta_x:
        dx = np.concatenate(delta_x)
        out["xcal_implied_angle_deg"] = {
            "median": float(np.degrees(np.median(dx))),
            "p95": float(np.degrees(np.percentile(dx, 95))),
            "max": float(np.degrees(dx.max())),
        }
    if casa_frame["elements"]:
        casa_frame["pass_class_c"] = casa_frame["fail"] == 0
        out["added_casa_frame_class_c"] = casa_frame
    if args.parang:
        fc = per_field.get(st.FIELDS[0][0], {})
        out["pass"] = bool(
            fc.get("fail", 1) == 0
            and out.get("xcal_implied_angle_deg", {}).get("median", 99) <= 0.3
            and flags_equal
            and data_equal
        )
    else:
        out["pass"] = bool(nfail == 0 and flags_equal and data_equal)
    out["seconds"] = time.perf_counter() - started
    st.write_json(args.out, out)
    print(json.dumps(out, indent=1, default=str))


def noise(args):
    started = time.perf_counter()
    d, meta, t, truth = load(args.vdir)
    vdir = Path(args.vdir)
    twin_prov = json.loads(
        Path(str(args.twin)[: -len(".ms")] + ".provenance.json").read_text()
    )
    ms_prov = json.loads(
        Path(str(args.ms)[: -len(".ms")] + ".provenance.json").read_text()
    )
    ms_ints = np.asarray(ms_prov["selection"]["integrations"])
    twin_ints = np.asarray(twin_prov["selection"]["integrations"])
    pos = {int(v): i for i, v in enumerate(ms_ints)}
    nant = len(d.antennas)
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    mask = np.load(vdir / (Path(args.ms).stem + ".rfi_mask.npz"))
    m_any = mask["any"]
    events = st.rfi_events(d, len(t["time"]))
    enu = st.enu_baselines(d)
    sky = meta["target_components"]
    cal = t["calibrator_stokes"]
    q = t["parallactic_angle"]
    n = 0
    s1 = 0.0
    s2 = 0.0
    max_full = 0.0
    max_twin = 0.0
    rfi_cells = 0
    for i, ti in enumerate(twin_ints):
        r0 = pos[int(ti)] * nbl
        full = read_rows(args.ms, "DATA", r0, nbl).astype(np.complex128)
        twin = read_rows(args.twin, "DATA", i * nbl, nbl).astype(np.complex128)
        bad = np.unpackbits(m_any[r0 : r0 + nbl], axis=1, count=d.nchan).astype(bool)
        diff = (full - twin)[~bad]
        parts = np.concatenate([diff.real.ravel(), diff.imag.ravel()])
        n += parts.size
        s1 += parts.sum()
        s2 += (parts**2).sum()
        rfi_cells += int(bad.sum())
        # Check 5: DATA recomputed from the truth and the seeds.
        rows = st.chunk_rows([ti], a1, a2)
        m, _ = st.sky_coherency(d, rows, t["uvw_antenna"], t["field"], sky, cal)
        v = st.corrupt(m, truth, d, rows, q)
        rfi = st.rfi_chunk(events, d, rows, enu)
        noise_ = st.noise_integration(d, ti, nbl)
        rec = (v + rfi + noise_).astype(np.complex64)
        max_full = max(max_full, float(np.abs(rec - full.astype(np.complex64)).max()))
        max_twin = max(
            max_twin,
            float(np.abs(v.astype(np.complex64) - twin.astype(np.complex64)).max()),
        )
    mean = s1 / n
    var = (s2 - n * mean**2) / (n - 1)
    sd = math.sqrt(var)
    sigma = d.sigma
    z = (sd - sigma) / (sigma / math.sqrt(2 * (n - 1)))
    z_mu = mean / (sigma / math.sqrt(n))
    out = {
        "ms": str(args.ms),
        "twin": str(args.twin),
        "integrations": len(twin_ints),
        "values": n,
        "rfi_cells_excluded": rfi_cells,
        "sigma_expected": sigma,
        "sigma_measured": sd,
        "ratio": sd / sigma,
        "z_std": z,
        "mean": mean,
        "z_mean": z_mu,
        "reconstruct_max_abs_diff_full": max_full,
        "reconstruct_max_abs_diff_twin": max_twin,
    }
    out["pass_noise"] = bool(abs(z) <= 3 and abs(z_mu) <= 3)
    out["pass_twin"] = bool(max_full == 0.0 and max_twin == 0.0)
    out["seconds"] = time.perf_counter() - started
    st.write_json(args.out, out)
    print(json.dumps(out, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("roundtrip")
    r.add_argument("vdir")
    r.add_argument("export")
    r.add_argument("twin")
    r.add_argument("out")
    r.add_argument("--parang", action="store_true")
    nz = sub.add_parser("noise")
    nz.add_argument("vdir")
    nz.add_argument("ms")
    nz.add_argument("twin")
    nz.add_argument("out")
    args = p.parse_args(argv)
    roundtrip(args) if args.cmd == "roundtrip" else noise(args)


if __name__ == "__main__":
    main()
