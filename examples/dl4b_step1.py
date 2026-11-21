"""DL4b (#42) step 1 (research/dl4b-step1.md): simulation and products.

simulate SEEDS_JSON OUT --workers N [--threads T] [--only NAMES]
    Per sky (shards of 10 in the seed table's order, done-markers): the MS by
    examples/gemclean_bench_simulate.py (recipe, 4096 x 1.5", sky and noise
    seeds), then WSClean 3.7 `-niter 0 -make-psf` (Briggs 0.5, MFS over the
    8 channels) for the dirty image and PSF. Kept: catalogue, dirty (float32),
    the central 1024^2 of the PSF (float32), the clean beam, timings. Training
    skies' MSs are deleted after imaging; V and G skies keep theirs.

prep SKIES_DIR --workers N
    Per simulated sky: the common beam b (rml_gap_score.halfmax_major_px on the
    PSF, the scorer's own rule) and the truth on the beam B * T at 4096^2
    (rml_gap_score.truth_on_beam, analytic, Jy per pixel): bt.npy, beam.json.

ladder SKIES SCRATCH --names V1,V2,... --arms W1,... [--threads 16] [--tag T]
    WSClean arms of section 3 per sky, sequentially at -j THREADS, from the
    sky's MS in SCRATCH; model and residual kept as npy; WSClean's own times.

opgate SKIES SCRATCH OUT_JSON
    Crop-operator gate (stage 3): for V1-V4, W1's model inside a 512^2 crop at
    the field centre and at a corner; its image through the 1024^2 PSF patch
    against WSClean's exact predict + inversion of the same crop model, inside
    the crop: relative rms error, median <= 0.10 at both positions.

score SKIES --names V1,... --arms W1,... OUT_JSON
    rml-gap's frozen measures (examples/rml_gap_score.py) per sky and arm: the
    truth control (band-limited truth, relative L2 <= 0.002, group ratios within
    0.002), then relative L2 on the beam, false flux (|model| outside every
    group) over the total true flux, extended groups failing measure 3, and
    positions; sigma from 1.4826 MAD of W1's residual outside every group.

parm SKIES SCRATCH --names V1,... --onnx LABEL=PATH --taus 3,5 --kmax 3
    Arm P (section 3): per sky and tau, passes k = 1..KMAX of the network
    (ONNX Runtime, 16 threads) with the beam threshold, each followed by
    WSClean -predict of the model; after pass k, `-continue` with W1's
    settings (scored as P at K = k), and the residual for pass k+1 by
    `-niter 0 -subtract-model`. Times of every step are kept.

WSClean runs as `wsclean` or $DL4B_WSCLEAN (see examples/dl4b_step0.py).
"""

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SIZE, SCALE = 4096, 1.5
IMG = ["-size", str(SIZE), str(SIZE), "-scale", f"{SCALE}asec", "-weight", "briggs", "0.5"]  # fmt: skip


def wsclean_cmd(work):
    tmpl = os.environ.get("DL4B_WSCLEAN")
    if not tmpl:
        return ["wsclean"]
    return shlex.split(tmpl.format(cwd=work, uid=f"{os.getuid()}:{os.getgid()}"))


def run(cmd, log, cwd):
    t = time.perf_counter()
    r = subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=cwd)
    Path(log).write_text(r.stdout + r.stderr)
    if r.returncode != 0:
        raise RuntimeError(
            f"{cmd[0]} rc {r.returncode}: {(r.stdout + r.stderr)[-800:]}"
        )
    return time.perf_counter() - t


def read(path):
    from astropy.io import fits

    with fits.open(path) as h:
        return np.asarray(h[0].data, np.float32)[0, 0], h[0].header


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sky(name, spec, out, threads):
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    # MS scratch on WSL's native disk ($DL4B_SCRATCH), not through 9P; products go to d
    scratch = Path(os.environ.get("DL4B_SCRATCH", str(d))) / name
    scratch.mkdir(parents=True, exist_ok=True)
    ms = scratch / f"{name}.ms"
    rec = {"name": name, **spec}
    if ms.exists():
        shutil.rmtree(ms)
    rec["simulate_s"] = run(
        [
            sys.executable,
            str(HERE / "gemclean_bench_simulate.py"),
            str(ms),
            "--sky",
            spec["recipe"],
            "--size",
            str(SIZE),
            "--scale",
            str(SCALE),
            "--sky-seed",
            str(spec["sky_seed"]),
            "--noise-seed",
            str(spec["noise_seed"]),
            "--catalogue",
            str(d / "catalogue.json"),
        ],
        d / "simulate.log",
        d,
    )
    rec["image_s"] = run(
        [
            *wsclean_cmd(scratch),
            "-j",
            str(threads),
            *IMG,
            "-niter",
            "0",
            "-make-psf",
            "-no-update-model-required",
            "-name",
            str(scratch / "d"),
            str(ms),
        ],
        d / "dirty.log",
        d,
    )
    dirty, _hdr = read(scratch / "d-dirty.fits")
    psf, phdr = read(scratch / "d-psf.fits")
    c = SIZE // 2
    np.save(d / "dirty.npy", dirty)
    np.save(d / "psf1024.npy", psf[c - 512 : c + 512, c - 512 : c + 512])
    rec["beam_deg"] = [phdr.get("BMAJ"), phdr.get("BMIN"), phdr.get("BPA")]
    rec["psf_peak_at_centre"] = bool(
        np.unravel_index(psf.argmax(), psf.shape) == (c, c)
    )
    for f in scratch.glob("d-*.fits"):
        if f.name != "d-dirty.fits":
            f.unlink()
    if name.startswith("T"):
        shutil.rmtree(ms)
        (scratch / "d-dirty.fits").unlink()
    rec["ms"] = str(ms) if ms.exists() else None
    (d / "sky.json").write_text(json.dumps(rec, indent=1))
    return rec


def shard(args):
    k, names, specs, out, threads = args
    done = out / f"shard-{k:03d}.done"
    js = out / f"shard-{k:03d}.json"
    if done.exists() and js.exists() and done.read_text() == sha(js):
        return k, "skip"
    t = time.perf_counter()
    try:
        recs = [sky(n, specs[n], out, threads) for n in names]
    except Exception as e:  # noqa: BLE001
        return k, f"FAILED {type(e).__name__}: {e}"
    js.write_text(json.dumps(recs, indent=1))
    done.write_text(sha(js))
    return k, f"{time.perf_counter() - t:.0f} s"


def simulate(a):
    specs = json.loads(Path(a.seeds).read_text())["skies"]
    names = [n for n in specs if not a.only or n in a.only.split(",")]
    # held-out and validation skies first, then training
    names = sorted(names, key=lambda n: (n[0] == "T", n))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(k, names[i : i + 10], specs, out, a.threads) for k, i in enumerate(range(0, len(names), 10))]  # fmt: skip
    with mp.get_context("spawn").Pool(a.workers, maxtasksperchild=1) as pool:
        for k, msg in pool.imap_unordered(shard, jobs):
            print(time.strftime("%H:%M:%S"), f"shard {k}: {msg}", flush=True)


COMMON = ["-niter", "10000000", "-no-update-model-required"]
W1 = ["-multiscale", "-auto-mask", "5", "-auto-threshold", "3", "-mgain", "0.8"]
ARMS = {
    "W1": W1,
    "W2": [*W1, "-multiscale-scales", "0,4,16,64"],
    "W3": [*W1, "-gain", "0.2"],
    "W4": [*W1, "-multiscale-scales", "0,4,16,64", "-gain", "0.2"],
    "W5": ["-multiscale", "-auto-mask", "5", "-auto-threshold", "3", "-mgain", "0.9"],
}


def ws_times(log):
    import re

    out = {}
    pat = r"(\d+):(\d+):([\d.]+)"
    m = re.search(r"Inversion: " + pat + r", prediction: " + pat + r", deconvolution: " + pat, log)  # fmt: skip
    if m:
        g = [float(x) for x in m.groups()]
        for j, k in enumerate(("inversion_s", "prediction_s", "deconvolution_s")):
            out[k] = g[3 * j] * 3600 + g[3 * j + 1] * 60 + g[3 * j + 2]
    m = re.search(r"(\d+) major iterations? (?:was|were) performed", log)
    out["major"] = int(m.group(1)) if m else None
    return out


def ladder(a):
    skies, scr = Path(a.skies), Path(a.scratch)
    for name in a.names.split(","):
        ms = scr / name / f"{name}.ms"
        for arm in a.arms.split(","):
            d = skies / name / "arms"
            d.mkdir(exist_ok=True)
            js = d / f"{arm}{a.tag}.json"
            if js.exists():
                continue
            w = scr / name
            t = time.perf_counter()
            run([*wsclean_cmd(w), "-j", str(a.threads), *IMG, *COMMON, *ARMS[arm], "-name", str(w / arm), str(ms)], d / f"{arm}{a.tag}.log", w)  # fmt: skip
            wall = time.perf_counter() - t
            rec = {"sky": name, "arm": arm, "wall_s": wall, **ws_times((d / f"{arm}{a.tag}.log").read_text())}  # fmt: skip
            np.save(d / f"{arm}-model.npy", read(w / f"{arm}-model.fits")[0])
            np.save(d / f"{arm}-residual.npy", read(w / f"{arm}-residual.fits")[0])
            for f in w.glob(f"{arm}-*.fits"):
                if not f.name.endswith(("-model.fits",)):
                    f.unlink()
            js.write_text(json.dumps(rec, indent=1))
            print(time.strftime("%H:%M:%S"), name, arm, f"{wall:.0f} s", rec.get("deconvolution_s"), flush=True)  # fmt: skip


def opgate(a):
    from astropy.io import fits
    from numpy.fft import irfft2, rfft2

    skies, scr = Path(a.skies), Path(a.scratch)
    res = []
    for name in ("V1", "V2", "V3", "V4"):
        w = scr / name
        ms = w / f"{name}.ms"
        model = np.load(skies / name / "arms" / "W1-model.npy")
        psf = np.load(skies / name / "psf1024.npy").astype(np.float64)
        hdr = fits.getheader(w / "W1-model.fits")
        for pos, (y0, x0) in (("centre", (1792, 1792)), ("corner", (256, 256))):
            m = np.zeros_like(model)
            m[y0 : y0 + 512, x0 : x0 + 512] = model[y0 : y0 + 512, x0 : x0 + 512]
            nm = f"gate-{pos}"
            fits.writeto(w / f"{nm}-model.fits", m[None, None].astype(np.float32), hdr, overwrite=True)  # fmt: skip
            run([*wsclean_cmd(w), "-j", "16", *IMG, "-predict", "-name", str(w / nm), str(ms)], skies / name / f"{nm}-p.log", w)  # fmt: skip
            run([*wsclean_cmd(w), "-j", "16", *IMG, "-niter", "0", "-no-update-model-required", "-data-column", "MODEL_DATA", "-name", str(w / (nm + "i")), str(ms)], skies / name / f"{nm}-i.log", w)  # fmt: skip
            exact = read(w / f"{nm}i-image.fits")[0][y0 : y0 + 512, x0 : x0 + 512].astype(np.float64)  # fmt: skip
            mc = np.zeros((1024, 1024))
            mc[:512, :512] = model[y0 : y0 + 512, x0 : x0 + 512]
            approx = irfft2(rfft2(mc) * rfft2(np.fft.ifftshift(psf)), s=(1024, 1024))[:512, :512]  # fmt: skip
            err = float(np.sqrt(np.mean((approx - exact) ** 2)) / max(np.sqrt(np.mean(exact**2)), 1e-30))  # fmt: skip
            res.append({"sky": name, "pos": pos, "rel_rms_err": err, "model_flux_in_crop": float(mc.sum())})  # fmt: skip
            for f in w.glob(f"{nm}*.fits"):
                f.unlink()
            print(name, pos, f"{err:.4f}", flush=True)
    med = {p: float(np.median([r["rel_rms_err"] for r in res if r["pos"] == p])) for p in ("centre", "corner")}  # fmt: skip
    out = {"per_crop": res, "median": med, "tolerance": 0.10, "pass": all(v <= 0.10 for v in med.values())}  # fmt: skip
    Path(a.out_json).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "per_crop"}))


def score(a):
    sys.path.insert(0, str(HERE))
    import rml_gap_score as R

    skies = Path(a.skies)
    out = {}
    for name in a.names.split(","):
        d = skies / name
        cat = json.loads((d / "catalogue.json").read_text())
        comps = R.components(cat)
        b = json.loads((d / "beam.json").read_text())["beam_px"]
        bt = np.load(d / "bt.npy").astype(np.float64)
        label, grps = R.groups(comps, SIZE, b)
        r1 = np.load(d / "arms" / "W1-residual.npy")
        outside = r1[label == 0]
        sigma = float(1.4826 * np.median(np.abs(outside - np.median(outside))))
        ftot = float(sum(c[2] for c in comps))
        bl = R.bandlimited_truth(comps, SIZE)
        rc = R.measures(R.model_on_beam(bl, b), bt, bl, label, grps, b, sigma)
        ratios = [g["F_M"] / g["F_T"] for g in rc["groups"]]
        control = {"relative_l2": rc["relative_l2"], "ratio_min": min(ratios), "ratio_max": max(ratios)}  # fmt: skip
        control["pass"] = bool(control["relative_l2"] <= 0.002 and abs(control["ratio_min"] - 1) <= 0.002 and abs(control["ratio_max"] - 1) <= 0.002)  # fmt: skip
        sky = {"beam_px": b, "sigma": sigma, "true_flux": ftot, "groups": len(grps), "extended_groups": sum(g["extended"] for g in grps), "control": control, "arms": {}}  # fmt: skip
        for arm in a.arms.split(","):
            mp_ = d / "arms" / f"{arm}-model.npy"
            if not mp_.exists():
                continue
            model = np.load(mp_).astype(np.float64)
            rec = R.measures(
                R.model_on_beam(model, b), bt, model, label, grps, b, sigma
            )
            ext = [g for g in rec["groups"] if g["extended"]]
            js = d / "arms" / f"{arm}.json"
            sky["arms"][arm] = {
                "relative_l2": rec["relative_l2"],
                "relative_l2_extended": rec.get("relative_l2_extended"),
                "relative_l2_points": rec.get("relative_l2_points"),
                "false_flux": rec["false_flux_abs"] / ftot,
                "extended_failing": sum(not g["flux_pass"] for g in ext),
                "positions_failed": len(rec["positions_failed"]),
                "model_flux": rec["model_flux_total"],
                **(json.loads(js.read_text()) if js.exists() else {}),
            }
            print(name, arm, {k: round(v, 4) if isinstance(v, float) else v for k, v in sky["arms"][arm].items() if k in ("relative_l2", "false_flux", "extended_failing", "deconvolution_s", "major", "wall_s")}, flush=True)  # fmt: skip
        out[name] = sky
        print(name, "control", control, flush=True)
    Path(a.out_json).write_text(json.dumps(out, indent=1))


def robust_rms(x):
    med = float(np.median(x))
    return max(1.4826 * float(np.median(np.abs(x - med))), 1e-12)


def peak_beam(model, beam_px):
    """B * m with B the circular common beam at peak 1 (Jy per beam)."""
    sys.path.insert(0, str(HERE))
    import rml_gap_score as R

    sb = beam_px * R.FWHM_TO_SIGMA
    return R.model_on_beam(model, beam_px) * (2 * np.pi * sb * sb)


def parm(a):
    import onnxruntime as ort
    from astropy.io import fits

    skies, scr = Path(a.skies), Path(a.scratch)
    label, path = a.onnx.split("=", 1)
    so = ort.SessionOptions()
    so.intra_op_num_threads = a.infer_threads
    sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
    for name in a.names.split(","):
        d, w = skies / name, scr / name
        ms = w / f"{name}.ms"
        b = json.loads((d / "beam.json").read_text())["beam_px"]
        hdr = fits.getheader(w / "W1-model.fits")
        dirty = np.load(d / "dirty.npy").astype(np.float32)
        for tau in [float(t) for t in a.taus.split(",")]:
            tag = f"P-{label}-t{tau:g}"
            js = d / "arms" / f"{tag}-K{a.kmax}.json"
            if js.exists():
                continue
            m = np.zeros_like(dirty)
            r = dirty
            steps = []
            for k in range(1, a.kmax + 1):
                st = {"k": k}
                s = robust_rms(r)
                t = time.perf_counter()
                y = sess.run(None, {"x": np.stack([r / s, m / s])[None].astype(np.float32)})[0][0, 0]  # fmt: skip
                st["infer_s"] = time.perf_counter() - t
                m = np.maximum(m + s * y, 0).astype(np.float32)
                keep = peak_beam(m.astype(np.float64), b) > a_tau(tau) * s
                m = np.where(keep, m, 0).astype(np.float32)
                st["model_flux"] = float(m.sum())
                st["model_pixels"] = int((m > 0).sum())
                nm = f"{tag}-K{k}"
                fits.writeto(w / f"{nm}-model.fits", m[None, None], hdr, overwrite=True)
                st["predict_s"] = run([*wsclean_cmd(w), "-j", "16", *IMG, "-predict", "-name", str(w / nm), str(ms)], d / "arms" / f"{nm}-p.log", w)  # fmt: skip
                t = time.perf_counter()
                run([*wsclean_cmd(w), "-j", "16", *IMG, *COMMON, *ARMS["W1"], "-continue", "-name", str(w / nm), str(ms)], d / "arms" / f"{nm}.log", w)  # fmt: skip
                st["continue_wall_s"] = time.perf_counter() - t
                st.update({f"continue_{k2}": v for k2, v in ws_times((d / "arms" / f"{nm}.log").read_text()).items()})  # fmt: skip
                np.save(d / "arms" / f"{nm}-model.npy", read(w / f"{nm}-model.fits")[0])
                np.save(d / "arms" / f"{nm}-proposal.npy", m)
                for f in w.glob(f"{nm}-*.fits"):
                    f.unlink()
                steps.append(st)
                (d / "arms" / f"{nm}.json").write_text(json.dumps({"sky": name, "arm": nm, "tau": tau, "steps": steps}, indent=1))  # fmt: skip
                print(time.strftime("%H:%M:%S"), name, nm, {kk: round(v, 1) if isinstance(v, float) else v for kk, v in st.items()}, flush=True)  # fmt: skip
                if k < a.kmax:
                    # the residual of m for the next pass: MODEL_DATA still holds m's
                    # prediction (-continue ran with -no-update-model-required)
                    t = time.perf_counter()
                    run([*wsclean_cmd(w), "-j", "16", *IMG, "-niter", "0", "-subtract-model", "-no-update-model-required", "-name", str(w / f"{nm}r"), str(ms)], d / "arms" / f"{nm}r.log", w)  # fmt: skip
                    steps[-1]["residual_s"] = time.perf_counter() - t
                    r = read(w / f"{nm}r-dirty.fits")[0]
                    for f in w.glob(f"{nm}r-*.fits"):
                        f.unlink()


def a_tau(tau):
    return tau


def prep_sky(d):
    sys.path.insert(0, str(HERE))
    import rml_gap_score as R

    if (d / "bt.npy").exists() and (d / "beam.json").exists():
        return d.name, "skip"
    psf = np.load(d / "psf1024.npy").astype(np.float64)
    b = R.halfmax_major_px(psf)
    cat = json.loads((d / "catalogue.json").read_text())
    bt = R.truth_on_beam(R.components(cat), SIZE, b).astype(np.float32)
    np.save(d / "bt.tmp.npy", bt)
    os.replace(d / "bt.tmp.npy", d / "bt.npy")
    (d / "beam.json").write_text(json.dumps({"beam_px": b, "true_flux": float(sum(c["flux"] for c in cat["components"]))}))  # fmt: skip
    return d.name, f"b={b:.3f} px"


def prep(a):
    dirs = sorted(p for p in Path(a.skies).iterdir() if (p / "sky.json").exists())
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for name, msg in pool.imap_unordered(prep_sky, dirs):
            print(time.strftime("%H:%M:%S"), name, msg, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("simulate")
    p.add_argument("seeds")
    p.add_argument("out")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--only")
    p.set_defaults(func=simulate)
    p = sub.add_parser("ladder")
    p.add_argument("skies")
    p.add_argument("scratch")
    p.add_argument("--names", required=True)
    p.add_argument("--arms", default="W1,W2,W3,W4,W5")
    p.add_argument("--threads", type=int, default=16)
    p.add_argument("--tag", default="")
    p.set_defaults(func=ladder)
    p = sub.add_parser("opgate")
    p.add_argument("skies")
    p.add_argument("scratch")
    p.add_argument("out_json")
    p.set_defaults(func=opgate)
    p = sub.add_parser("score")
    p.add_argument("skies")
    p.add_argument("out_json")
    p.add_argument("--names", required=True)
    p.add_argument("--arms", default="W1,W2,W3,W4,W5")
    p.set_defaults(func=score)
    p = sub.add_parser("parm")
    p.add_argument("skies")
    p.add_argument("scratch")
    p.add_argument("--names", required=True)
    p.add_argument("--onnx", required=True)
    p.add_argument("--taus", default="3,5")
    p.add_argument("--kmax", type=int, default=3)
    p.add_argument("--infer-threads", type=int, default=16)
    p.set_defaults(func=parm)
    p = sub.add_parser("prep")
    p.add_argument("skies")
    p.add_argument("--workers", type=int, default=4)
    p.set_defaults(func=prep)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
