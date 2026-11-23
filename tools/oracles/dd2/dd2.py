# SPDX-License-Identifier: MIT
"""DD2: facet predict and imaging with per-facet gains (research/dd2-facet-imaging.md).

    python tools/oracles/dd2/dd2.py prepare SIMDIR RUN
    python tools/oracles/dd2/dd2.py rang RUN
    python tools/oracles/dd2/dd2.py compare RUN

`prepare` solves DD1's DATA with the frozen DD cap (150, 1e-7, 0.99), writes
the facet regions (RUN/facets.reg), the H5parms (RUN/h5/{unit,c2,solved}.h5),
the model image (RUN/model.fits, WSClean orientation) and RUN/prepare.json
(guards, dropped components, P3 under the frozen rule). `rang` computes
rang's predictions and facet images (RUN/rang.npz). `compare` reads
WSClean's outputs (RUN/wsc: MODEL_DATA as .npy, FITS images) and evaluates
the controls C0-C2 and arms H, P and I into RUN/compare.json.
"""

import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

NX = NY = 2400
SCALE_ARCSEC = 4.0
EDGE_PX = 3
CAP = {"max_iterations": 150, "stop_criterion": 1e-7, "stop_fraction": 0.99}
EPS = 1e-7
TOL_P = 1e-4
TOL_I = 1e-3
C2_GAIN = (2.0, 0.5 * np.exp(1j * np.pi / 4))
C2_FACET = 1
HERE = Path(__file__).resolve().parent
ARCSEC = math.pi / (180 * 3600)
DELTA = SCALE_ARCSEC * ARCSEC


def _dd1():
    path = HERE.parent / "dd1" / "compare.py"
    spec = importlib.util.spec_from_file_location("dd1_compare", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_ms(ms):
    from rang import core_ms

    t = core_ms.open_table(str(ms))
    c = {
        k: t.getcol(k)
        for k in (
            "TIME", "ANTENNA1", "ANTENNA2", "UVW", "DATA", "DATA_NF",
            "WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW",
        )
    }  # fmt: skip
    c["MODEL"] = np.stack([t.getcol(f"MODEL_D{d}") for d in range(4)], axis=2)
    ant = core_ms.open_table(str(Path(ms) / "ANTENNA"))
    c["ant_names"] = [str(n) for n in ant.getcol("NAME")]
    c["ant_pos"] = np.asarray(ant.getcol("POSITION"), float)
    fld = core_ms.open_table(str(Path(ms) / "FIELD"))
    c["phase_dir"] = np.asarray(fld.getcol("PHASE_DIR"), float).reshape(-1, 2)[0]
    spw = core_ms.open_table(str(Path(ms) / "SPECTRAL_WINDOW"))
    c["freq"] = np.asarray(spw.getcol("CHAN_FREQ"), float).reshape(-1)
    return c


# -- facets ---------------------------------------------------------------------


def centres_lm(truth):
    return np.asarray(truth["centres_deg"], float) * math.pi / 180


def clip(poly, a, b):
    """Sutherland-Hodgman: keep the part of `poly` with a . p <= b."""
    out = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        fp, fq = a @ p - b, a @ q - b
        if fp <= 0:
            out.append(p)
        if fp * fq < 0:
            out.append(p + (q - p) * (fp / (fp - fq)))
    return out


def voronoi_polygons(centres):
    """Voronoi cells of `centres` (lm, radians) clipped to the image square."""
    half_l = NX / 2 * DELTA
    half_m = NY / 2 * DELTA
    box = [np.array(v) for v in ((-half_l, -half_m), (half_l, -half_m),
                                 (half_l, half_m), (-half_l, half_m))]  # fmt: skip
    polys = []
    for i, ci in enumerate(centres):
        poly = box
        for j, cj in enumerate(centres):
            if i != j:
                a = 2 * (cj - ci)
                poly = clip(poly, a, cj @ cj - ci @ ci)
        polys.append(poly)
    return polys


def radec(l, m, ra0, dec0):
    n = math.sqrt(1.0 - l * l - m * m)
    dec = math.asin(m * math.cos(dec0) + n * math.sin(dec0))
    ra = ra0 + math.atan2(l, n * math.cos(dec0) - m * math.sin(dec0))
    return ra % (2 * math.pi), dec


def region_text(polys, centres, phase_dir):
    ra0, dec0 = phase_dir
    lines = ["# Region file format: DS9 version 4.1", "global color=green", "fk5"]
    for k, (poly, c) in enumerate(zip(polys, centres, strict=True)):
        verts = []
        for p in poly:
            ra, dec = radec(p[0], p[1], ra0, dec0)
            verts += [f"{math.degrees(ra):.10f}", f"{math.degrees(dec):.10f}"]
        lines.append(f"polygon({','.join(verts)}) # text=d{k}")
        ra, dec = radec(c[0], c[1], ra0, dec0)
        lines.append(f"point({math.degrees(ra):.10f},{math.degrees(dec):.10f})")
    return "\n".join(lines) + "\n"


def pixel_lm():
    """(l, m) of every pixel of a WSClean FITS image, shape (NY, NX):
    l = (NX/2 - x) delta (RA increases to the left), m = (y - NY/2) delta."""
    x = np.arange(NX)
    y = np.arange(NY)
    l = (NX / 2 - x) * DELTA
    m = (y - NY / 2) * DELTA
    return np.broadcast_to(l[None, :], (NY, NX)), np.broadcast_to(m[:, None], (NY, NX))


def facet_index_and_margin(l, m, centres):
    """Nearest centre (Voronoi cell) of each point and its distance (pixels)
    to the cell boundary."""
    pts = np.stack([np.asarray(l), np.asarray(m)], -1)
    d2 = ((pts[..., None, :] - centres) ** 2).sum(-1)
    order = np.argsort(d2, axis=-1)
    i1, i2 = order[..., 0], order[..., 1]
    c1, c2 = centres[i1], centres[i2]
    margin = (np.take_along_axis(d2, i2[..., None], -1)[..., 0]
              - np.take_along_axis(d2, i1[..., None], -1)[..., 0]) / (
        2 * np.linalg.norm(c1 - c2, axis=-1))  # fmt: skip
    return i1, margin / DELTA


# -- gains and H5parm -------------------------------------------------------------


def interval_axes(c, ti=4):
    utime, tindex = np.unique(c["TIME"], return_inverse=True)
    nint = math.ceil(len(utime) / ti)
    centres = np.array([utime[k * ti : (k + 1) * ti].mean() for k in range(nint)])
    return utime, tindex, tindex // ti, centres


def write_h5(path, gains, flags, c, centres_t, centres):
    from rang.formats import h5parm

    gains = np.array(gains, complex)
    weights = np.ones(gains.shape)
    if flags is not None:
        bad = np.broadcast_to(flags[..., None] != 0, gains.shape)
        gains[bad] = 1.0
        weights[bad] = 0.0
    ra0, dec0 = c["phase_dir"]
    dirs = [(f"d{k}", radec(cc[0], cc[1], ra0, dec0)) for k, cc in enumerate(centres)]
    ss = h5parm.diagonal_solset(
        gains, centres_t, [float(c["freq"].mean())], c["ant_names"],
        positions=c["ant_pos"], directions=dirs, weights=weights,
    )  # fmt: skip
    h5parm.write(path, {"sol000": ss})
    back = h5parm.diagonal_gains(h5parm.read(path)["sol000"])
    return bool(np.array_equal(back, np.abs(gains) * np.exp(1j * np.angle(gains))))


def prepare(sim, run):
    from rang import cal_gain, core_grid

    run.mkdir(parents=True, exist_ok=False)
    (run / "h5").mkdir()
    dd1 = _dd1()
    c = read_ms(Path(sim) / "dd1.ms")
    truth = dict(np.load(Path(sim) / "truth.npz"))
    nant = len(c["ant_names"])
    centres = centres_lm(truth)
    utime, _tindex, block, centres_t = interval_axes(c)
    record = {"note": "research/dd2-facet-imaging.md", "cap": CAP}
    # Guards (section 3).
    nearest = np.abs(utime[:, None] - centres_t[None]).argmin(1)
    record["guard_nearest_time"] = bool(
        np.array_equal(nearest, np.arange(len(utime)) // 4)
    )
    t0 = time.perf_counter()
    sol = cal_gain.solve_dd(
        c["DATA"], c["MODEL"], c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
        c["ANTENNA1"], c["ANTENNA2"], block, nant=nant, refant=0, **CAP,
    )  # fmt: skip
    record["solve"] = {
        "iterations": sol.iterations,
        "converged_fraction": sol.converged_fraction,
        "flagged": int(sol.flags.sum()),
        "seconds": time.perf_counter() - t0,
    }
    p3 = cal_gain.solve_dd(
        c["DATA_NF"], c["MODEL"], c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
        c["ANTENNA1"], c["ANTENNA2"], block, nant=nant, refant=0, **CAP,
    )  # fmt: skip
    p3d = {"gains": p3.gains, "flags": p3.flags}
    record["P3_under_cap"] = {
        "iterations": p3.iterations,
        "converged_fraction": p3.converged_fraction,
        "truth": dd1.truth_stat(p3d, truth, "P3", nant),
    }
    p1d = {"gains": sol.gains, "flags": sol.flags}
    record["P1_under_cap_truth"] = dd1.truth_stat(p1d, truth, "P1", nant)
    np.savez(run / "gains.npz", gains=sol.gains, flags=sol.flags, centres_t=centres_t)
    unit = np.ones_like(sol.gains)
    c2 = unit.copy()
    c2[:, :, :, C2_FACET, 0] = C2_GAIN[0]
    c2[:, :, :, C2_FACET, 1] = C2_GAIN[1]
    record["H_roundtrip"] = {
        name: write_h5(run / "h5" / f"{name}.h5", g, f, c, centres_t, centres)
        for name, g, f in (("unit", unit, None), ("c2", c2, None),
                           ("solved", sol.gains, sol.flags))
    }  # fmt: skip
    from rang.formats import h5parm

    names = set(h5parm.read(run / "h5" / "solved.h5")["sol000"].soltabs["amplitude000"]
                .axis_values["ant"].tolist())  # fmt: skip
    record["guard_antennas"] = all(a in names for a in c["ant_names"])
    polys = voronoi_polygons(centres)
    (run / "facets.reg").write_text(
        region_text(polys, centres, c["phase_dir"]), encoding="utf-8"
    )
    # Model image: components snapped to pixel centres, flat spectrum.
    lm, flux = truth["lm"], truth["flux"]
    x = np.rint(NX / 2 - lm[:, 0] / DELTA).astype(int)
    y = np.rint(NY / 2 + lm[:, 1] / DELTA).astype(int)
    lp, mp = (NX / 2 - x) * DELTA, (y - NY / 2) * DELTA
    fidx, margin = facet_index_and_margin(lp, mp, centres)
    keep = margin >= EDGE_PX
    model = np.zeros((NY, NX))
    np.add.at(model, (y[keep], x[keep]), flux[keep])
    record["components"] = {
        "kept": int(keep.sum()),
        "dropped_near_boundary": int((~keep).sum()),
        "per_facet": np.bincount(fidx[keep], minlength=len(centres)).tolist(),
    }
    hdr = core_grid.wcs_header(c["phase_dir"], NX, NY, SCALE_ARCSEC, c["freq"])
    hdr["BUNIT"] = "JY/PIXEL"
    core_grid.write_fits(run / "model.fits", model, hdr)
    np.save(run / "model.npy", model)
    (run / "prepare.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record))


# -- rang's side ------------------------------------------------------------------


def facet_masks(centres):
    l, m = pixel_lm()
    idx, margin = facet_index_and_margin(l, m, centres)
    return idx, margin


def predict(c, model, idx, gains, block, nfacet):
    """sum_f G_p,f M_f G_q,f^H (XX, YY; cross hands zero); gains None: the
    whole model, unit gains."""
    from rang import core_wgridder

    out = np.zeros(c["DATA"].shape, complex)
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    parts = [None] if gains is None else range(nfacet)
    for f in parts:
        img = model if f is None else np.where(idx == f, model, 0.0)
        v = core_wgridder.dirty2vis(
            uvw=c["UVW"], freq=c["freq"], dirty=np.ascontiguousarray(img.T),
            pixsize_x=DELTA, pixsize_y=DELTA, epsilon=EPS, flip_v=True, flip_w=True,
        )  # fmt: skip
        if f is None:
            out[..., 0] += v
            out[..., 3] += v
            continue
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]  # (rows, 2)
        out[..., 0] += gp[:, None, 0] * v * np.conj(gq[:, None, 0])
        out[..., 3] += gp[:, None, 1] * v * np.conj(gq[:, None, 1])
    return out


def correction(gp, gq, w, candidate):
    """Facet normalisation c (section 4) over rows; gains constant over
    channels, w the per-cell Stokes I weight (rows, chans)."""
    ax, ay = np.abs(gp[:, 0]) ** 2, np.abs(gp[:, 1]) ** 2
    bx, by = np.abs(gq[:, 0]) ** 2, np.abs(gq[:, 1]) ** 2
    if candidate == "a":
        s = 0.5 * (ax * bx + ay * by)
    else:
        s = 0.25 * (ax + ay) * (bx + by)
    wr = w.sum(1)
    return float((s * wr).sum() / wr.sum())


def facet_image(c, idx, gains, block, nfacet, candidate):
    """Stitched (dirty, image) in WSClean's FITS orientation; gains None: no
    facets, no correction."""
    from rang import core_wgridder

    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    w = c["WEIGHT_SPECTRUM"][..., 0].astype(np.float64)
    data = c["DATA"].astype(np.complex128)

    def grid(vis):
        return core_wgridder.fits_image(
            c["UVW"], c["freq"], vis, w, NX, NY, SCALE_ARCSEC, epsilon=EPS
        )["dirty"]

    if gains is None:
        img = grid(0.5 * (data[..., 0] + data[..., 3]))
        return img, img, {}
    dirty = np.zeros((NY, NX))
    image = np.zeros((NY, NX))
    norms = {}
    for f in range(nfacet):
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]
        xx = np.conj(gp[:, None, 0]) * data[..., 0] * gq[:, None, 0]
        yy = np.conj(gp[:, None, 1]) * data[..., 3] * gq[:, None, 1]
        img = grid(0.5 * (xx + yy))
        cf = correction(gp, gq, w, candidate)
        norms[f"d{f}"] = cf
        sel = idx == f
        dirty[sel] = img[sel] / math.sqrt(cf)
        image[sel] = img[sel] / cf
    return dirty, image, norms


def rang_side(run):
    sim = Path(json.loads((run / "sim.json").read_text())["sim"])
    c = read_ms(sim / "dd1.ms")
    truth = dict(np.load(sim / "truth.npz"))
    centres = centres_lm(truth)
    _, _, block, _ = interval_axes(c)
    g = np.load(run / "gains.npz")
    solved = g["gains"]
    unit = np.ones_like(solved)
    c2 = unit.copy()
    c2[:, :, :, C2_FACET, 0] = C2_GAIN[0]
    c2[:, :, :, C2_FACET, 1] = C2_GAIN[1]
    model = np.load(run / "model.npy")
    idx, _ = facet_masks(centres)
    out, secs = {}, {}
    t = time.perf_counter()
    out["P_C0"] = predict(c, model, idx, None, block, 4)
    out["P_C1"] = predict(c, model, idx, unit, block, 4)
    secs["predict_C0"] = time.perf_counter() - t
    t = time.perf_counter()
    out["P_P"] = predict(c, model, idx, solved, block, 4)
    secs["predict_P"] = time.perf_counter() - t
    norms = {}
    t = time.perf_counter()
    out["I_C0_dirty"], out["I_C0_image"], _ = facet_image(c, idx, None, block, 4, "a")
    secs["image_C0"] = time.perf_counter() - t
    for name, gains in (("C1", unit), ("C2", c2), ("I", solved)):
        for cand in ("a", "b"):
            t = time.perf_counter()
            d, i, n = facet_image(c, idx, gains, block, 4, cand)
            secs[f"image_{name}_{cand}"] = time.perf_counter() - t
            out[f"I_{name}_{cand}_dirty"], out[f"I_{name}_{cand}_image"] = d, i
            norms[f"{name}_{cand}"] = n
    np.savez(run / "rang.npz", **{k: v.astype(np.complex64 if k.startswith("P_") else np.float32)
                                  for k, v in out.items()})  # fmt: skip
    (run / "rang.json").write_text(
        json.dumps({"seconds": secs, "norms": norms}, indent=1)
    )
    print(json.dumps({"seconds": secs, "norms": norms}))


# -- comparison -------------------------------------------------------------------


def p_gate(vr, vw):
    vr, vw = np.asarray(vr, complex), np.asarray(vw, complex)
    scale = float(np.abs(vr[..., [0, 3]]).max())
    par = float(np.abs(vr[..., [0, 3]] - vw[..., [0, 3]]).max())
    cross = float(max(np.abs(vr[..., [1, 2]]).max(), np.abs(vw[..., [1, 2]]).max()))
    return {
        "max_abs_parallel": par,
        "rel_parallel": par / scale,
        "max_abs_cross": cross,
        "pass": bool(par <= TOL_P * scale and cross <= TOL_P * scale),
    }


def i_gate(ir, iw, interior, facet=None, idx=None):
    sel = interior if facet is None else interior & (idx == facet)
    peak = float(np.abs(iw).max())
    d = np.abs(np.asarray(ir, float) - np.asarray(iw, float))
    inner = float(d[sel].max())
    band = float(d[~interior].max()) if (~interior).any() else 0.0
    return {
        "peak_wsc": peak,
        "max_abs_interior": inner,
        "rel_interior": inner / peak,
        "rel_boundary_band": band / peak,
        "pass": bool(inner <= TOL_I * peak),
    }


def read_fits(path):
    from astropy.io import fits

    return np.asarray(fits.getdata(str(path)), float)[0, 0]


def compare(run):
    sim = Path(json.loads((run / "sim.json").read_text())["sim"])
    truth = dict(np.load(sim / "truth.npz"))
    centres = centres_lm(truth)
    idx, margin = facet_masks(centres)
    xg, yg = np.meshgrid(np.arange(NX), np.arange(NY))
    interior = (margin >= EDGE_PX) & (xg >= EDGE_PX) & (xg < NX - EDGE_PX) & (
        yg >= EDGE_PX) & (yg < NY - EDGE_PX)  # fmt: skip
    r = np.load(run / "rang.npz")
    w = run / "wsc"
    rec = {"note": "research/dd2-facet-imaging.md"}
    # Predict controls and arm P.
    for case in ("C0", "C1", "P"):
        vw = np.load(w / f"predict-{case}.npy")
        rec[f"predict_{case}"] = p_gate(r[f"P_{case}"], vw)
    # Imaging controls.
    rec["image_C0"] = {
        kind: i_gate(r["I_C0_dirty"], read_fits(w / f"image-C0-{kind}.fits"), interior)
        for kind in ("dirty", "image")
    }
    rec["image_C1"] = {
        kind: i_gate(
            r[f"I_C1_a_{kind}"], read_fits(w / f"image-C1-{kind}.fits"), interior
        )
        for kind in ("dirty", "image")
    }
    c2 = {}
    for cand in ("a", "b"):
        c2[cand] = {
            kind: i_gate(
                r[f"I_C2_{cand}_{kind}"],
                read_fits(w / f"image-C2-{kind}.fits"),
                interior,
                C2_FACET,
                idx,
            )
            for kind in ("dirty", "image")
        }
    rec["image_C2"] = c2
    chosen = [k for k in ("a", "b") if all(v["pass"] for v in c2[k].values())]
    rec["C2_candidate"] = chosen[0] if len(chosen) == 1 else None
    rec["controls_pass"] = bool(
        rec["predict_C0"]["pass"] and rec["predict_C1"]["pass"]
        and all(v["pass"] for v in rec["image_C0"].values())
        and all(v["pass"] for v in rec["image_C1"].values())
        and rec["C2_candidate"] is not None
    )  # fmt: skip
    if rec["C2_candidate"]:
        k = rec["C2_candidate"]
        rec["arm_I"] = {
            kind: i_gate(
                r[f"I_I_{k}_{kind}"], read_fits(w / f"image-I-{kind}.fits"), interior
            )
            for kind in ("dirty", "image")
        }
    rec["arm_P"] = rec["predict_P"]
    (run / "compare.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0]
    if cmd == "prepare":
        run = Path(argv[2])
        prepare(Path(argv[1]), run)
        (run / "sim.json").write_text(json.dumps({"sim": str(Path(argv[1]))}))
    elif cmd == "rang":
        rang_side(Path(argv[1]))
    elif cmd == "compare":
        compare(Path(argv[1]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
