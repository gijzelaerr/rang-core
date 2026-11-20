"""DL4b (#42) step 0, nash side (research/dl4b-step0.md).

Subcommands:

psfg DATA OUT --workers N [--shards A-B]
    Per seed, the 512^2 grid PSF (note section 0.5): remake the seed's MS as
    examples/astrodeconv_sim.py does (DATA = the flux-10 visibilities), image
    it once (-niter 0; the dirty must match the stored dirty to 1e-4 of its
    peak), then 9 delta models at {0,128,255}^2 through WSClean -predict and a
    256^2 uniform -niter 0 inversion. Each offset is taken from the delta that
    puts the output pixel nearest the centre. Shards of 10 seeds:
    psfg-KKK.npz (G float32 (10,512,512)), .json, .done (npz sha256).

optol DATA PSFG OUT_JSON
    Operator tolerance (note section 2.2): for the 90 validation seeds,
    flux 1000, rms(dirty - G (*) model_b - residual_b) / rms(residual_b).
"""

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import astrodeconv_sim as A

POS = (0, 128, 255)


def wsclean_cmd(work):
    """WSClean's argv prefix: `wsclean`, or $DL4B_WSCLEAN with {cwd} and {uid}
    filled (glacier: a docker run of rang-wsclean-native:3.7 with /dev/shm mounted)."""
    import os
    import shlex

    tmpl = os.environ.get("DL4B_WSCLEAN")
    if not tmpl:
        return ["wsclean"]
    return shlex.split(tmpl.format(cwd=work, uid=f"{os.getuid()}:{os.getgid()}"))


TOL_DIRTY = 1e-4


def ws(args, work, name):
    t = time.perf_counter()
    r = subprocess.run(
        [*wsclean_cmd(work), "-j", "1", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=work,
    )
    if r.returncode != 0:
        raise RuntimeError(f"wsclean {name}: {(r.stdout + r.stderr)[-1500:]}")
    return time.perf_counter() - t


def read(path):
    from astropy.io import fits

    return np.asarray(fits.getdata(path), np.float32)[0, 0]


def pick():
    """Offset d in -256..255 -> the delta position whose y0 + d is nearest 128."""
    d = np.arange(-256, 256)
    out = []
    for dd in d:
        ok = [q for q in POS if 0 <= q + dd <= 255]
        out.append(min(ok, key=lambda q: abs(q + dd - 128)) if ok else -1)
    return d, np.array(out)


def assemble(imgs):
    d, pk = pick()
    G = np.zeros((512, 512), np.float32)
    for iy, dy in enumerate(d):
        y0 = pk[iy]
        if y0 < 0:
            continue
        for x0 in POS:
            xs = np.where(pk == x0)[0]
            G[iy, xs] = imgs[(y0, x0)][y0 + dy, x0 + d[xs]]
    return G


def remake_ms(seed, work, flux=10, col="DATA"):
    """The seed's MS with one data column, as astrodeconv_sim.simulate_seed."""
    p = A.randomize(seed, flux)
    text = A.skymodel_text(seed, p)
    ra0, dec0 = math.radians(A.JOB["ra"]), math.radians(p["dec"])
    A.FIELD_DEC[0] = dec0
    names = [a[0] for a in A.SPIEL_ANTENNAS]
    xyz = np.array([a[1:] for a in A.SPIEL_ANTENNAS])
    ndump = math.floor(p["synthesis"] * 3600 / A.JOB["dtime"])
    times, uvw, _ = A.track(xyz, ra0, dec0, ndump, A.JOB["dtime"])
    a1, a2 = np.triu_indices(len(names), 1)
    uvw_rows = (uvw[:, a2] - uvw[:, a1]).reshape(-1, 3)
    a1r = np.tile(a1, ndump).astype(np.int32)
    a2r = np.tile(a2, ndump).astype(np.int32)
    sigma = A.JOB["sefd"] / math.sqrt(2 * A.JOB["dtime"] * p["dfreq"])
    data = A.noisy(A.predict(text, uvw_rows, ra0, dec0), sigma, seed, flux)
    ms = work / "f.ms"
    A.write_ms(ms, xyz, names, times, uvw_rows, a1r, a2r, {col: data}, sigma, A.JOB["freq0"], float(p["dfreq"]))  # fmt: skip
    return ms


def base(work):
    return ["-size", "256", "256", "-scale", f"{A.CELL_ASEC}asec", "-weight", "uniform", "-temp-dir", str(work), "-reorder"]  # fmt: skip


def psfg_seed(seed, dirty_f10):
    from astropy.io import fits

    t0 = time.perf_counter()
    work = Path(tempfile.mkdtemp(prefix=f"g{seed:04d}-", dir="/dev/shm"))
    try:
        ms = remake_ms(seed, work)
        b = base(work)
        ws(b + ["-niter", "0", "-data-column", "DATA", "-name", "d", str(ms)], work, "d")  # fmt: skip
        d = read(work / "d-image.fits")
        dirty_err = float(np.abs(d - dirty_f10).max() / np.abs(dirty_f10).max())
        hdr = fits.getheader(work / "d-image.fits")
        imgs = {}
        for y0 in POS:
            for x0 in POS:
                m = np.zeros((256, 256), np.float32)
                m[y0, x0] = 1.0
                nm = f"g{y0}_{x0}"
                fits.writeto(work / f"{nm}-model.fits", m[None, None], hdr)
                ws(b + ["-predict", "-data-column", "DATA", "-name", nm, str(ms)], work, nm)  # fmt: skip
                ws(b + ["-niter", "0", "-data-column", "MODEL_DATA", "-name", nm + "i", str(ms)], work, nm + "i")  # fmt: skip
                imgs[(y0, x0)] = read(work / f"{nm}i-image.fits")
        G = assemble(imgs)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return G, {
        "seed": seed,
        "dirty_err_rel_peak": dirty_err,
        "dirty_ok": dirty_err <= TOL_DIRTY,
        "peak": float(G[256, 256]),
        "wall_s": time.perf_counter() - t0,
    }


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def psfg_shard(k, data, out, dirty10=None):
    npz = out / f"psfg-{k:03d}.npz"
    done = out / f"psfg-{k:03d}.done"
    if done.exists() and npz.exists() and done.read_text().strip() == sha(npz):
        return k, "skip"
    t = time.perf_counter()
    if dirty10:
        dirty = np.load(dirty10)[f"d{k:03d}"]
    else:
        dirty = np.load(data / f"shard-{k:03d}.npz")["dirty"][0::3]
    Gs, recs = [], []
    for i in range(10):
        G, rec = psfg_seed(10 * k + i, dirty[i])
        Gs.append(G)
        recs.append(rec)
    tmp = out / f"psfg-{k:03d}.tmp.npz"
    np.savez(tmp, G=np.stack(Gs))
    tmp.rename(npz)
    (out / f"psfg-{k:03d}.json").write_text(json.dumps({"shard": k, "seeds": recs, "wall_s": time.perf_counter() - t}, indent=1))  # fmt: skip
    done.write_text(sha(npz))
    return (
        k,
        f"{time.perf_counter() - t:.0f} s, dirty ok {sum(r['dirty_ok'] for r in recs)}/10",
    )


def _worker(a):
    try:
        return psfg_shard(*a)
    except Exception as e:  # noqa: BLE001
        return a[0], f"FAILED {type(e).__name__}: {e}"


def shards_arg(s):
    if not s:
        return list(range(300))
    a, _, b = s.partition("-")
    return list(range(int(a), int(b or a) + 1))


def psfg(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(k, Path(args.data), out, args.dirty10) for k in shards_arg(args.shards)]
    ctx = mp.get_context("spawn")
    with ctx.Pool(args.workers, maxtasksperchild=1) as pool:
        for k, msg in pool.imap_unordered(_worker, jobs):
            print(time.strftime("%H:%M:%S"), f"psfg shard {k}: {msg}", flush=True)


def conv(m, G):
    from numpy.fft import irfft2, rfft2

    M = np.zeros((512, 512))
    M[:256, :256] = m
    c = irfft2(rfft2(M) * rfft2(np.fft.ifftshift(G.astype(float))), s=(512, 512))
    return c[:256, :256]


def optol(args):
    data, pg = Path(args.data), Path(args.psfg)
    split = read_split(data)
    seeds = sorted(s for s, v in split.items() if v == "validation")
    errs = []
    for s in seeds:
        k, i = divmod(s, 10)
        z = np.load(data / f"shard-{k:03d}.npz")
        G = np.load(pg / f"psfg-{k:03d}.npz")["G"][i]
        fi = 3 * i + 2
        e = z["dirty"][fi] - conv(z["model_b"][fi], G) - z["residual_b"][fi]
        errs.append(
            {"seed": s, "err_rms_rel": float(e.std() / z["residual_b"][fi].std())}
        )
    med = float(np.median([e["err_rms_rel"] for e in errs]))
    res = {"n": len(errs), "median_err_rms_rel": med, "tolerance": 0.10, "pass": med <= 0.10, "per_seed": errs}  # fmt: skip
    Path(args.out_json).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "per_seed"}))


COMMON = ["-niter", "100000000", "-auto-threshold", "0.125", "-auto-mask", "5", "-no-update-model-required"]  # fmt: skip
LADDER = {
    "WA": ["-mgain", "1.0"],
    "W1": ["-mgain", "0.8"],
    "W2": ["-mgain", "0.8", "-gain", "0.2"],
    "W3": ["-mgain", "0.8", "-auto-threshold", "1"],
    "W4": ["-mgain", "0.9"],
    "W5": ["-mgain", "0.8", "-multiscale"],
    "W6": ["-mgain", "0.8", "-multiscale", "-multiscale-scales", "0,4", "-gain", "0.2"],
}
RE_T = r"(\d+):(\d+):([\d.]+)"


def ws_times(log):
    import re

    out = {}
    m = re.search(r"Inversion: " + RE_T + r", prediction: " + RE_T + r", deconvolution: " + RE_T, log)  # fmt: skip
    if m:
        g = [float(x) for x in m.groups()]
        for j, k in enumerate(("inversion_s", "prediction_s", "deconvolution_s")):
            out[k] = g[3 * j] * 3600 + g[3 * j + 1] * 60 + g[3 * j + 2]
    m = re.search(r"(\d+) major iterations? (?:was|were) performed", log)
    out["major"] = int(m.group(1)) if m else None
    m = re.search(r"Performed (\d+) iterations in total", log)
    out["iterations"] = int(m.group(1)) if m else 0
    return out


def remake_ms3(seed, work):
    """The seed's MS with DATA_F10/100/1000, exactly as simulate_seed writes it."""
    p = A.randomize(seed, 10)
    ra0, dec0 = math.radians(A.JOB["ra"]), math.radians(p["dec"])
    A.FIELD_DEC[0] = dec0
    names = [a[0] for a in A.SPIEL_ANTENNAS]
    xyz = np.array([a[1:] for a in A.SPIEL_ANTENNAS])
    ndump = math.floor(p["synthesis"] * 3600 / A.JOB["dtime"])
    times, uvw, _ = A.track(xyz, ra0, dec0, ndump, A.JOB["dtime"])
    a1, a2 = np.triu_indices(len(names), 1)
    uvw_rows = (uvw[:, a2] - uvw[:, a1]).reshape(-1, 3)
    a1r = np.tile(a1, ndump).astype(np.int32)
    a2r = np.tile(a2, ndump).astype(np.int32)
    sigma = A.JOB["sefd"] / math.sqrt(2 * A.JOB["dtime"] * p["dfreq"])
    cols = {}
    for f in A.FLUX_SETS:
        text = A.skymodel_text(seed, A.randomize(seed, f))
        cols[f"DATA_F{f}"] = A.noisy(
            A.predict(text, uvw_rows, ra0, dec0), sigma, seed, f
        )
    cols["RESID"] = np.zeros_like(cols["DATA_F10"])
    cols["DATA"] = np.zeros_like(
        cols["DATA_F10"]
    )  # WSClean -predict needs a DATA column
    ms = work / "field.ms"
    A.write_ms(ms, xyz, names, times, uvw_rows, a1r, a2r, cols, sigma, A.JOB["freq0"], float(p["dfreq"]))  # fmt: skip
    return ms


def wsbase(work):
    return ["-size", "256", "256", "-scale", f"{A.CELL_ASEC}asec", "-weight", "uniform", "-temp-dir", str(work), "-reorder"]  # fmt: skip


def ws_logged(args, work, name):
    t = time.perf_counter()
    r = subprocess.run([*wsclean_cmd(work), "-j", "1", *args], check=False, capture_output=True, text=True, cwd=work)  # fmt: skip
    wall = time.perf_counter() - t
    log = r.stdout + r.stderr
    (work / f"{name}.log").write_text(log)
    if r.returncode != 0:
        raise RuntimeError(f"wsclean {name}: {log[-1500:]}")
    return wall, log


def beam_kernel(beam, n=33):
    """As examples/dl4b_train.py beam_kernels (numpy, one beam)."""
    maj, mn, pa = beam
    cell = A.CELL_ASEC / 3600
    sx, sy, pa = mn / cell / 2.3548, maj / cell / 2.3548, math.radians(pa)
    h = n // 2
    yy, xx = np.mgrid[-h : h + 1, -h : h + 1].astype(float)
    east, north = -xx, yy
    u = east * math.cos(pa) - north * math.sin(pa)
    v = east * math.sin(pa) + north * math.cos(pa)
    return np.exp(-0.5 * ((u / sx) ** 2 + (v / sy) ** 2))


def conv_same(x, k):
    """Linear convolution, output the size of x (scipy's fftconvolve 'same')."""
    from numpy.fft import irfft2, rfft2

    n, h = x.shape[0] + k.shape[0] - 1, k.shape[0] // 2
    y = irfft2(rfft2(x.astype(float), (n, n)) * rfft2(k, (n, n)), (n, n))
    return y[h : h + x.shape[0], h : h + x.shape[1]]


def field_scores(model, residual, truth, comps, beam):
    """Section 5 measures; comps rows (x, y, I, inside) of all 100 sources."""
    bpx = beam[0] / (A.CELL_ASEC / 3600)
    inside = comps[:, 3] > 0
    tin = float(comps[inside, 2].sum())
    yy, xx = np.nonzero(model)
    vals = model[yy, xx]
    if vals.size:
        dd = (xx[:, None] - comps[None, :, 0]) ** 2 + (yy[:, None] - comps[None, :, 1]) ** 2  # fmt: skip
        near = dd.argmin(1)
        dist = np.sqrt(dd[np.arange(len(near)), near])
        rec = float(vals[(dist <= bpx) & inside[near]].sum())
        false = float(np.abs(vals[dist > 2 * bpx]).sum())
    else:
        rec = false = 0.0
    k = beam_kernel(beam)
    e1 = float(np.abs(conv_same(model - truth, k)).sum())
    return {
        "tin": tin,
        "recovery": rec / tin if tin > 0 else None,
        "false": false / tin if tin > 0 else None,
        "e1_raw": e1,
        "e1": e1 / tin if tin > 0 else None,
        "e2": float(np.sqrt(np.mean(residual.astype(float) ** 2))),
        "model_flux": float(vals.sum()),
        "model_pixels": int(vals.size),
    }


def sparse(img):
    idx = np.flatnonzero(img)
    return idx.astype(np.int32), img.reshape(-1)[idx].astype(np.float32)


def ladder_seed(seed, z, i, bm, out_dir, keep_logs=False):
    """All ladder arms, empty and truth arms for one seed's three fields."""
    from astropy.io import fits

    work = Path(tempfile.mkdtemp(prefix=f"L{seed:04d}-", dir="/dev/shm"))
    recs, models = [], {}
    try:
        t = time.perf_counter()
        ms = remake_ms3(seed, work)
        t_ms = time.perf_counter() - t
        b = wsbase(work)
        for j, f in enumerate(A.FLUX_SETS):
            fi = 3 * i + j
            col = f"DATA_F{f}"
            dirty0, truth = z["dirty"][fi], z["truth"][fi]
            comps = z["components"][fi][:, [4, 5, 2, 6]]
            beam = bm[(seed, f)]
            rec = {"seed": seed, "flux": f, "ms_s": t_ms}
            wall, log = ws_logged(b + ["-niter", "0", "-data-column", col, "-name", f"d{f}", str(ms)], work, f"d{f}")  # fmt: skip
            d = read(work / f"d{f}-image.fits")
            rec["dirty_err_rel_peak"] = float(
                np.abs(d - dirty0).max() / np.abs(dirty0).max()
            )
            rec["dirty_bit_identical"] = bool(np.array_equal(d, dirty0))
            rec["Z"] = {**field_scores(np.zeros_like(d), d, truth, comps, beam), "major": 1, "wall_s": wall}  # fmt: skip
            for arm, extra in LADDER.items():
                args = (
                    b
                    + COMMON
                    + extra
                    + ["-data-column", col, "-name", f"{arm}{f}", str(ms)]
                )
                # later flags win in WSClean's parser: W3's -auto-threshold 1 follows COMMON
                wall, log = ws_logged(args, work, f"{arm}{f}")
                m = read(work / f"{arm}{f}-model.fits")
                r = read(work / f"{arm}{f}-residual.fits")
                rec[arm] = {**field_scores(m, r, truth, comps, beam), **ws_times(log), "wall_s": wall}  # fmt: skip
                rec[arm]["log_tail"] = [x for x in log.splitlines() if "iteration" in x.lower()][-6:]  # fmt: skip
                models[f"{arm}_f{f}"] = sparse(m)
                if keep_logs:
                    (out_dir / "log-sample").mkdir(exist_ok=True)
                    (out_dir / "log-sample" / f"s{seed}-{arm}{f}.log").write_text(log)
            # truth arm through the exact cycle
            hdr = fits.getheader(work / f"d{f}-image.fits")
            fits.writeto(work / f"T{f}-model.fits", truth[None, None].astype(np.float32), hdr)  # fmt: skip
            rec["T"] = exact_residual_score(work, ms, b, col, f"T{f}", truth, truth, comps, beam)  # fmt: skip
            recs.append(rec)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return recs, models


def exact_residual(work, ms, b, col, name):
    """Model NAME-model.fits -> exact residual image (WSClean predict, DATA - MODEL, -niter 0)."""
    from rang import core_ms_write as W

    t = time.perf_counter()
    ws_logged(b + ["-predict", "-data-column", col, "-name", name, str(ms)], work, name + "p")  # fmt: skip
    with W.Table(ms) as tb:
        tb.putcol("RESID", tb.getcol(col) - tb.getcol("MODEL_DATA"))
    ws_logged(b + ["-niter", "0", "-data-column", "RESID", "-name", name + "r", str(ms)], work, name + "r")  # fmt: skip
    return read(work / f"{name}r-image.fits"), time.perf_counter() - t


def exact_residual_score(work, ms, b, col, name, model, truth, comps, beam):
    r, wall = exact_residual(work, ms, b, col, name)
    return {**field_scores(model, r, truth, comps, beam), "cycle_s": wall}


def ladder(args):
    data, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    split = read_split(data)
    bm = beams(data)
    seeds = sorted(s for s, v in split.items() if v in ("validation", "test"))
    groups = [seeds[g : g + 10] for g in range(0, len(seeds), 10)]
    jobs = [(g, data, out, bm, split) for g in groups]
    ctx = mp.get_context("spawn")
    with ctx.Pool(args.workers, maxtasksperchild=1) as pool:
        for name, msg in pool.imap_unordered(_ladder_worker, jobs):
            print(time.strftime("%H:%M:%S"), f"ladder {name}: {msg}", flush=True)


def _ladder_worker(a):
    group, data, out, bm, split = a
    name = f"L{group[0]:04d}"
    try:
        done = out / f"{name}.done"
        js = out / f"{name}.json"
        if done.exists() and js.exists() and done.read_text().strip() == sha(js):
            return name, "skip"
        t = time.perf_counter()
        recs, models = [], {}
        for s in group:
            k, i = divmod(s, 10)
            z = np.load(data / f"shard-{k:03d}.npz")
            r, m = ladder_seed(s, z, i, bm, out, keep_logs=s == group[0])
            for x in r:
                x["split"] = split[s]
            recs += r
            models.update({f"s{s}_{key}_{part}": v[p] for key, v in m.items() for p, part in enumerate(("idx", "val"))})  # fmt: skip
        np.savez(out / f"{name}-models.npz", **models)
        js.write_text(json.dumps(recs))
        done.write_text(sha(js))
        return name, f"{time.perf_counter() - t:.0f} s"
    except Exception as e:  # noqa: BLE001
        return name, f"FAILED {type(e).__name__}: {e}"


P_MAX = 6


def robust_rms(x):
    med = np.median(x)
    return max(1.4826 * float(np.median(np.abs(x - med))), 1e-12)


def net_session(path):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


def net_field(sess, kind, ms, work, b, col, hdr, d, truth, comps, beam, name):
    """N1: one pass; NP: passes with the exact cycle between, stop rule of
    note section 5. Per pass: measures on (m_p, exact residual after p)."""
    from astropy.io import fits

    m = np.zeros_like(d, dtype=np.float32)
    r = d.astype(np.float32)
    passes = []
    for p in range(1 if kind == "N1" else P_MAX):
        s = robust_rms(r)
        x = np.stack([r / s, m / s])[None].astype(np.float32)
        t = time.perf_counter()
        y = sess.run(None, {"x": x})[0][0, 0]
        t_inf = time.perf_counter() - t
        m_new = np.maximum(m + s * y, 0).astype(np.float32)
        change = float(np.abs(m_new - m).sum())
        m = m_new
        fits.writeto(work / f"{name}p{p}-model.fits", m[None, None], hdr, overwrite=True)  # fmt: skip
        r, t_cyc = exact_residual(work, ms, b, col, f"{name}p{p}")
        passes.append({**field_scores(m, r, truth, comps, beam), "infer_s": t_inf, "cycle_s": t_cyc})  # fmt: skip
        if change < 0.01 * float(np.abs(m).sum()):
            break
    last = dict(passes[-1])
    last["passes"] = len(passes)
    last["inversions"] = len(passes) + 1
    last["infer_s_total"] = sum(q["infer_s"] for q in passes)
    last["per_pass"] = passes
    return last, m


def netscore(args):
    data, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.split == "test" and not (out / "choices.json").exists():
        sys.exit("test split: write OUT/choices.json (W*, checkpoints) first")
    nets = [n.split("=", 1) for n in args.net]  # LABEL=KIND:PATH
    split = read_split(data)
    bm = beams(data)
    seeds = sorted(s for s, v in split.items() if v == args.split)
    groups = [seeds[g : g + 10] for g in range(0, len(seeds), 10)]
    jobs = [(g, data, out, bm, nets) for g in groups]
    ctx = mp.get_context("spawn")
    with ctx.Pool(args.workers, maxtasksperchild=1) as pool:
        for name, msg in pool.imap_unordered(_net_worker, jobs):
            print(time.strftime("%H:%M:%S"), f"netscore {name}: {msg}", flush=True)


def _net_worker(a):
    from astropy.io import fits

    group, data, out, bm, nets = a
    name = f"N{group[0]:04d}"
    try:
        done, js = out / f"{name}.done", out / f"{name}.json"
        if done.exists() and js.exists() and done.read_text().strip() == sha(js):
            return name, "skip"
        t0 = time.perf_counter()
        sess = {lab: (kp.split(":", 1)[0], net_session(kp.split(":", 1)[1])) for lab, kp in nets}  # fmt: skip
        recs, models = [], {}
        for s in group:
            k, i = divmod(s, 10)
            z = np.load(data / f"shard-{k:03d}.npz")
            work = Path(tempfile.mkdtemp(prefix=f"N{s:04d}-", dir="/dev/shm"))
            try:
                ms = remake_ms3(s, work)
                b = wsbase(work)
                for j, f in enumerate(A.FLUX_SETS):
                    fi = 3 * i + j
                    col = f"DATA_F{f}"
                    ws_logged(b + ["-niter", "0", "-data-column", col, "-name", f"d{f}", str(ms)], work, f"d{f}")  # fmt: skip
                    d = read(work / f"d{f}-image.fits")
                    hdr = fits.getheader(work / f"d{f}-image.fits")
                    rec = {"seed": s, "flux": f, "dirty_err_rel_peak": float(np.abs(d - z["dirty"][fi]).max() / np.abs(z["dirty"][fi]).max())}  # fmt: skip
                    comps = z["components"][fi][:, [4, 5, 2, 6]]
                    for lab, (kind, se) in sess.items():
                        rec[lab], m = net_field(se, kind, ms, work, b, col, hdr, d, z["truth"][fi], comps, bm[(s, f)], f"{lab}{f}")  # fmt: skip
                        idx, val = sparse(m)
                        models[f"s{s}_{lab}_f{f}_idx"], models[f"s{s}_{lab}_f{f}_val"] = idx, val  # fmt: skip
                    recs.append(rec)
            finally:
                shutil.rmtree(work, ignore_errors=True)
        np.savez(out / f"{name}-models.npz", **models)
        js.write_text(json.dumps(recs))
        done.write_text(sha(js))
        return name, f"{time.perf_counter() - t0:.0f} s"
    except Exception as e:  # noqa: BLE001
        return name, f"FAILED {type(e).__name__}: {e}"


def read_split(data):
    lines = (data.parent / "split.csv").read_text().split()[1:]
    return {int(a): b for a, b in (line.split(",") for line in lines)}


def beams(data):
    import csv
    import gzip

    path = data / "manifest.csv"
    opener = open if path.exists() else gzip.open
    path = path if path.exists() else Path(str(path) + ".gz")
    with opener(path, "rt") as f:
        return {
            (int(r["seed"]), int(r["flux"])): (
                float(r["beam_a_maj"]),
                float(r["beam_a_min"]),
                float(r["beam_a_pa"]),
            )
            for r in csv.DictReader(f)
        }


def pack(args):
    """Training packs for glacier: train and validation seeds only (the test
    split never leaves nash). pack-KKK.npz: seed, flux, split (0 train,
    1 validation), dirty, truth as (flat index, value) with -1 padding, comps (x, y, I, inside), beam (deg, deg, deg),
    (G per seed is read from the psfg shards by the trainer)."""
    data, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    split = read_split(data)
    bm = beams(data)
    n = 0
    for k in shards_arg(args.shards):
        dst = out / f"pack-{k:03d}.npz"
        if dst.exists():
            continue
        z = np.load(data / f"shard-{k:03d}.npz")
        keep = [i for i in range(10) if split[10 * k + i] != "test"]
        fi = [3 * i + j for i in keep for j in range(3)]
        seeds = np.array([10 * k + i for i in keep for _ in range(3)], np.int32)
        flux = np.array([f for _ in keep for f in A.FLUX_SETS], np.int32)
        comps = z["components"][fi][:, :, [4, 5, 2, 6]].astype(np.float32)
        truth = z["truth"][fi].reshape(len(fi), -1)
        tidx = np.full((len(fi), 100), -1, np.int32)
        tval = np.zeros((len(fi), 100), np.float32)
        for j, row in enumerate(truth):
            nz = np.flatnonzero(row)
            tidx[j, : nz.size], tval[j, : nz.size] = nz, row[nz]
        tmp = out / f"pack-{k:03d}.tmp.npz"
        np.savez(
            tmp,
            seed=seeds,
            flux=flux,
            split=np.array([split[s] == "validation" for s in seeds], np.int8),
            dirty=z["dirty"][fi],
            tidx=tidx,
            tval=tval,
            comps=comps,
            beam=np.array(
                [bm[(int(s), int(f))] for s, f in zip(seeds, flux)], np.float64
            ),
        )
        tmp.rename(dst)
        n += 1
    print(f"packs written: {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ladder")
    p.add_argument("data")
    p.add_argument("out")
    p.add_argument("--workers", type=int, default=1)
    p.set_defaults(func=ladder)
    p = sub.add_parser("netscore")
    p.add_argument("data")
    p.add_argument("out")
    p.add_argument("--split", choices=("validation", "test"), required=True)
    p.add_argument(
        "--net", action="append", required=True, help="LABEL=N1|NP:PATH.onnx"
    )
    p.add_argument("--workers", type=int, default=1)
    p.set_defaults(func=netscore)
    p = sub.add_parser("pack")
    p.add_argument("data")
    p.add_argument("out")
    p.add_argument("--shards")
    p.set_defaults(func=pack)
    p = sub.add_parser("psfg")
    p.add_argument("data")
    p.add_argument("out")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--shards")
    p.add_argument(
        "--dirty10", help="npz of flux-10 dirty images d{KKK} (no shards needed)"
    )
    p.set_defaults(func=psfg)
    p = sub.add_parser("optol")
    p.add_argument("data")
    p.add_argument("psfg")
    p.add_argument("out_json")
    p.set_defaults(func=optol)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
