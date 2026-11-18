# SPDX-License-Identifier: MIT
"""The runs of research/stop28-default.md (issue #28 at GeMClean's shipping accuracy), on nash.

Every simulation, preparation, GeMClean, WSClean and scoring command runs under
`nice -n 19 ionice -c3` through the main checkout's heavy lock. Run each stage from an
unattended driver (setsid nohup); its log ends with `DRIVER-END <stage> rc=N`.

Usage: python examples/stop28_default.py STAGE
    regen     S1-S3, H1-H8 simulated again; main-table and noise hashes against the archive
    simulate  H9-H16 (the blind skies), once
    seen      S1-S3 (D, R and -stop-tolerance 0 for I1), H1-H8: prepare and run
    new       H9-H16: prepare and run D, R
    wsclean   H9-H16: WSClean 3.7 fast and plain
    pilot     the pilot runs (cal2 A at 3 and 1 mJy, cal3 B at 3 mJy)
    score     every scorer, the pilot's included
    table     the measures, I1, I2 and the frozen verdict -> O/summary.json

Confirmation leg (amendment 4), O = the new run root, PREV = the 2026-11-17 run root:
    c-bin       the H9-H16 binary copied from PREV and hash-checked
    c-seen      S1-S3: WSClean nominres dirty image and PSF, prepare --wsclean-dirty, D, R, e0,
                scores with the scorer's own beam (O/beam-s123.json records the source)
    c-simulate  H17-H24, once (refuses to run before c-seen has scored S1-S3)
    c-new       H17-H24: prepare and run D, R
    c-wsclean   H17-H24: WSClean fast and plain
    c-score     H17-H24 scores
    c-table     the amendment-4 verdict on H17-H24 alone -> O/summary.json

Paths from the environment, with nash's defaults: O (outputs), W (this worktree), BIN, LOCK,
WSCLEAN (nash's system WSClean 3.7).
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
O = Path(os.environ.get("O", HOME / "rang-data/outputs/stop28-default-20261117"))
W = Path(os.environ.get("W", Path(__file__).resolve().parents[1]))
PY = str(W / ".venv/bin/python")
BIN = os.environ.get("BIN", str(O / "bin/gemclean"))
LOCK = os.environ.get("LOCK", str(HOME / "Github/rang/tools/heavy_lock.py"))
WSCLEAN = os.environ.get("WSCLEAN", "/usr/bin/wsclean")
EX = W / "examples"
EPS = 0.02
T = 100e-6
SEEN = ["s1", "s2", "s3", "h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8"]
NEW = [f"h{i}" for i in range(9, 17)]
PILOT = (
    ("cal2.ms", "0.003", "a-3mjy"),
    ("cal3.ms", "0.003", "b-3mjy"),
    ("cal2.ms", "0.001", "a-1mjy"),
)
FITS = ("model", "residual", "image", "psf", "dirty")
# Amendment 4: the confirmation leg.
PREV = Path(os.environ.get("PREV", HOME / "rang-data/outputs/stop28-default-20261117"))
CONFIRM_NEW = [f"h{i}" for i in range(17, 25)]
S123 = ["s1", "s2", "s3"]
BIN_SHA256 = "d242ef6800523838a411d6f0818c5579afa8e2efb7296ca96af606b42f4f2857"
ARCHIVED_S_BEAM = 10.761531523459142
CONFIRM = False


def size_of(s):
    return 4096 if s == "h3" else 2048


def locked(cmd, slots, mem, log, env=None):
    """Run cmd at nice 19 / idle IO under the heavy lock; a row in O/timing.tsv."""
    argv = [sys.executable, LOCK, "run", "--slots", str(slots), "--mem", str(mem)]
    argv += ["--", "nice", "-n", "19", "ionice", "-c3"] + [str(c) for c in cmd]
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as f:
        code = subprocess.run(
            argv,
            stdout=f,
            stderr=subprocess.STDOUT,
            check=False,
            env={**os.environ, **(env or {})},
        ).returncode
    wall = time.time() - t0
    with open(O / "timing.tsv", "a", encoding="utf-8") as f:
        f.write(f"{Path(log).stem}\t{wall:.1f}\t{code}\t{slots}\t{mem}\n")
    print(
        Path(log).stem, "exit", code, f"{wall:.0f} s (lock wait included)", flush=True
    )
    return code


def gem(d, name, ms, size, tol=None, scale="1.5asec", thr="100e-6", mem=6):
    """One GeMClean run at the shipping accuracy (no -wgridder-accuracy), -j 4."""
    d.mkdir(parents=True, exist_ok=True)
    if (d / f"{name}-report.json").exists():
        print(name, "exists", flush=True)
        return 0
    cmd = [BIN, "-no-update-model-required", "-name", d / name]
    cmd += ["-size", size, size, "-scale", scale, "-weight", "briggs", "0.5"]
    cmd += ["-niter", "1000000", "-gain", "0.1", "-nmiter", "1000"]
    cmd += ["-abs-threshold", thr, "-data-column", "DATA", "-field", "0", "-j", "4"]
    if tol is not None:
        cmd += ["-stop-tolerance", tol]
    cmd.append(ms)
    (d / f"{name}.cmd").write_text(" ".join(map(str, cmd)) + "\n", encoding="utf-8")
    return locked(cmd, 4, mem, d / f"{name}.log")


def simulate_one(s, size):
    data = O / "data"
    data.mkdir(parents=True, exist_ok=True)
    ms = data / f"{s}.ms"
    if (data / f"{s}.json").exists():
        return
    cmd = [PY, EX / "gemclean_bench_simulate.py", ms, "--sky", s.upper()]
    cmd += ["--size", size, "--scale", "1.5", "--catalogue", data / f"{s}.json"]
    cmd += ["--noise-out", data / f"{s}.noise.c64"]
    locked(cmd, 2, 6, O / "logs" / f"simulate-{s}.log")


def regen():
    """S1-S3, H1-H8 from their recipes; compare hashes with the archived catalogues."""
    out = {}
    for s in SEEN:
        arch = json.loads((O / "in/cat" / f"{s}.json").read_text(encoding="utf-8"))
        for k, v in (("nant", 64), ("nchan", 8), ("dt_s", 8.0), ("hours", 2.0)):
            assert arch[k] == v, (s, k, arch[k])
        simulate_one(s, arch["image"]["size"])
        new = json.loads((O / "data" / f"{s}.json").read_text(encoding="utf-8"))
        a = {k: v for k, v in arch["main_table_sha256"].items() if k != "table.lock"}
        b = {k: v for k, v in new["main_table_sha256"].items() if k != "table.lock"}
        rec = {"main_table": a == b}
        if "noise_out_sha256" in arch:
            rec["noise"] = arch["noise_out_sha256"] == new["noise_out_sha256"]
        out[s] = rec
        print(s, rec, flush=True)
    (O / "data" / "regen-check.json").write_text(json.dumps(out, indent=1))


def prepare(s, wsclean_dirty=None):
    prep = O / "prep" / s
    if (prep / "vis.c128").exists():
        return
    cmd = [PY, EX / "gemclean_bench_compare.py", "prepare", O / "data" / f"{s}.ms"]
    cmd += [O / "data" / f"{s}.json", prep, "--size", size_of(s), "--scale", "1.5"]
    cmd += ["--noise", O / "data" / f"{s}.noise.c64"]
    if wsclean_dirty:
        cmd += ["--wsclean-dirty", wsclean_dirty]
    locked(cmd, 4, 12, O / "logs" / f"prepare-{s}.log")


def pair(stage, s, extra_e0=False):
    d = O / stage
    ms = O / "data" / f"{s}.ms"
    mem = 12 if size_of(s) == 4096 else 6
    gem(d, f"{s}-default", ms, size_of(s), mem=mem)
    gem(d, f"{s}-e{EPS:g}", ms, size_of(s), tol=EPS, mem=mem)
    if extra_e0:
        gem(d, f"{s}-e0", ms, size_of(s), tol=0, mem=mem)


def wsclean():
    d = O / "wsclean"
    (d / "ms").mkdir(parents=True, exist_ok=True)
    (d / "tmp").mkdir(exist_ok=True)
    for s in NEW:
        ms = d / "ms" / f"{s}.ms"
        if not ms.exists():
            shutil.copytree(O / "data" / f"{s}.ms", ms)
        for loop, slots in (("fast", 8), ("hogbom", 3)):
            name = f"{s}-abs-nominres-{loop}-j8"
            if (d / f"{name}-image.fits").exists():
                continue
            args = ["-gridder", "wgridder", "-data-column", "DATA", "-field", "0"]
            args += ["-size", "2048", "2048", "-scale", "1.5asec"]
            args += ["-weight", "briggs", "0.5", "-pol", "I", "-j", "8"]
            args += ["-no-update-model-required", "-temp-dir", d / "tmp"]
            args += ["-niter", "1000000", "-nmiter", "0", "-gain", "0.1"]
            args += ["-mgain", "0.8", "-abs-threshold", "0.0001"]
            args += ["-no-min-grid-resolution", "-wgridder-accuracy", "1e-6"]
            if loop == "hogbom":
                args.append("-no-fast-subminor")
            # Amendment 2: the native image needs AVX-512; nash runs its system WSClean 3.7.
            cmd = [WSCLEAN, *args]
            cmd += ["-name", d / name, ms]
            (d / f"{name}.cmd").write_text(" ".join(map(str, cmd)) + "\n")
            locked(cmd, slots, 8, d / f"{name}.log", env={"OMP_NUM_THREADS": "8"})
    shutil.rmtree(d / "tmp", ignore_errors=True)


def fits_header(path):
    out = {}
    with open(path, "rb") as f:
        while True:
            block = f.read(2880).decode("ascii")
            for i in range(0, 2880, 80):
                card = block[i : i + 80]
                key = card[:8].strip()
                if key == "END":
                    return out
                if card[8:10] == "= ":
                    try:
                        out[key] = float(card[10:].split("/")[0])
                    except ValueError:
                        pass


def beam_of(s):
    """research/gemclean-stop28.md amendment 3; S1-S3 the scorer's own (amendment 3 here)."""
    if CONFIRM and s in S123:
        # Amendment 4: the scorer's own beam from the prep's WSClean PSF fit (None),
        # the archived beam only if c-seen found no fit (recorded before H17-H24).
        rec = json.loads((O / "beam-s123.json").read_text(encoding="utf-8"))
        return rec["beam_arcsec_passed"][s]
    if CONFIRM and s in CONFIRM_NEW:
        h = fits_header(O / "wsclean" / f"{s}-abs-nominres-fast-j8-image.fits")
        return (h["BMAJ"] * h["BMIN"]) ** 0.5 * 3600.0
    if s in ("s1", "s2", "s3"):
        # Amendment 3 (post hoc): the beam the scorer took from the archived prep's
        # WSClean dirty image, beam_arcsec of D:/rang/outputs/stop28-20261116/scores/dev-s*.json.
        return 10.761531523459142
    if s in ("h1", "h2", "h3", "h4"):
        f = O / "in/scores" / f"gemclean-{s}.json"
    elif s in ("h5", "h6", "h7", "h8"):
        f = O / "in/scores" / f"new-{s}.json"
    elif s in NEW:
        h = fits_header(O / "wsclean" / f"{s}-abs-nominres-fast-j8-image.fits")
        return (h["BMAJ"] * h["BMIN"]) ** 0.5 * 3600.0
    else:
        return None
    return json.loads(f.read_text(encoding="utf-8"))["beam_arcsec"]


def score_one(s, run_dir, out, jobs):
    if Path(out).exists():
        return
    cmd = [PY, EX / "gemclean_bench_compare.py", "score", O / "prep" / s]
    cmd += [O / "data" / f"{s}.json", run_dir, out, "--jobs", *jobs]
    b = beam_of(s)
    if b is not None:
        cmd += ["--beam-arcsec", f"{b:.6f}"]
    locked(cmd, 2, 12, O / "logs" / f"score-{Path(out).stem}.log")


def pilot():
    d = O / "pilot"
    for ms, thr, name in PILOT:
        for t, tag in ((None, "default"), (EPS, f"e{EPS:g}")):
            gem(
                d,
                f"{name}-{tag}",
                O / "in/pilot" / ms,
                4096,
                tol=t,
                scale="3asec",
                thr=thr,
                mem=20,
            )


def pscore():
    tool = EX / "gemclean_heldout_real.py"
    d = O / "pilot"
    t = f"e{EPS:g}"
    for ms, prep, names in (
        ("cal2.ms", "prep-a", ["a-3mjy", "a-1mjy"]),
        ("cal3.ms", "prep-b", ["b-3mjy"]),
    ):
        if not (O / prep / "meta.json").exists():
            cmd = [PY, "-I", tool, "prep", O / "in/pilot" / ms, O / prep]
            cmd += ["--size", "4096", "--scale", "3"]
            locked(cmd, 4, 24, O / "logs" / f"{prep}.log")
        for n in names:
            jobs = [f"{n}-default", f"{n}-{t}"]
            out = O / "scores" / f"pilot-{n}.json"
            if not out.exists():
                cmd = [PY, "-I", tool, "score", O / prep, d, out, "--job", *jobs]
                locked(cmd, 4, 16, O / "logs" / f"pscore-{n}.log")
            out = O / "scores" / f"pilot-compare-{n}.json"
            if not out.exists():
                cmd = [PY, "-I", tool, "compare", O / prep, d, out]
                cmd += [O / "pilot-images" / n, "--job", *jobs, "--beam-arcsec", "12.7"]
                cmd += ["--mask-sigma", "5", "--compact-sigma", "10"]
                locked(cmd, 4, 16, O / "logs" / f"pcompare-{n}.log")


def score():
    (O / "scores").mkdir(exist_ok=True)
    t = f"e{EPS:g}"
    for s in SEEN:
        score_one(
            s, O / "seen", O / "scores" / f"seen-{s}.json", [f"{s}-default", f"{s}-{t}"]
        )
    for s in NEW:
        score_one(
            s, O / "new", O / "scores" / f"new-{s}.json", [f"{s}-default", f"{s}-{t}"]
        )
        jobs = [f"{s}-abs-nominres-fast-j8", f"{s}-abs-nominres-hogbom-j8"]
        score_one(s, O / "wsclean", O / "scores" / f"wsclean-{s}.json", jobs)
    pscore()


# --- confirmation leg (amendment 4) -----------------------------------------


def c_bin():
    src, dst = PREV / "bin/gemclean", O / "bin/gemclean"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
        for f in ("commit.txt", "gemclean.sha256"):
            shutil.copy2(PREV / "bin" / f, O / "bin" / f)
    got = hashlib.sha256(dst.read_bytes()).hexdigest()
    print("bin sha256", got, "expected", BIN_SHA256, flush=True)
    if got != BIN_SHA256:
        raise SystemExit("binary hash mismatch: the leg stops (amendment 4)")


def link_seen_data(s):
    data = O / "data"
    data.mkdir(parents=True, exist_ok=True)
    for ext in (".ms", ".json", ".noise.c64"):
        dst = data / f"{s}{ext}"
        if not dst.exists():
            dst.symlink_to(PREV / "data" / f"{s}{ext}")


def wsclean_dirty(s):
    """-niter 0 -make-psf at the nominres settings (gemclean_bench_run.sh dirty/nominres/fast)."""
    d = O / "wsclean"
    (d / "ms").mkdir(parents=True, exist_ok=True)
    (d / "tmp").mkdir(exist_ok=True)
    ms = d / "ms" / f"{s}.ms"
    if not ms.exists():
        shutil.copytree(O / "data" / f"{s}.ms", ms)
    name = f"{s}-dirty-nominres-fast-j8"
    if not (d / f"{name}-psf.fits").exists():
        args = ["-gridder", "wgridder", "-data-column", "DATA", "-field", "0"]
        args += ["-size", "2048", "2048", "-scale", "1.5asec"]
        args += ["-weight", "briggs", "0.5", "-pol", "I", "-j", "8"]
        args += ["-no-update-model-required", "-temp-dir", d / "tmp"]
        args += ["-niter", "0", "-make-psf"]
        args += ["-no-min-grid-resolution", "-wgridder-accuracy", "1e-6"]
        cmd = [WSCLEAN, *args, "-name", d / name, ms]
        (d / f"{name}.cmd").write_text(" ".join(map(str, cmd)) + "\n")
        locked(cmd, 8, 8, d / f"{name}.log", env={"OMP_NUM_THREADS": "8"})
    return d / name


def psf_fits(s):
    meta = json.loads((O / "prep" / s / "meta.json").read_text(encoding="utf-8"))
    out = []
    for k, c in sorted(meta.get("comparisons", {}).items()):
        a, b = c.get("psf_bmaj_arcsec"), c.get("psf_bmin_arcsec")
        if "nominres" in k and a and b and math.isfinite(a) and math.isfinite(b):
            out.append(math.sqrt(a * b))
    return out


def c_seen():
    rec = {
        "rule": "amendment 4: the scorer's own beam (null passed); archived beam only without a fit",
        "beam_arcsec_passed": {},
        "scorer_fit_arcsec": {},
    }
    for s in S123:
        link_seen_data(s)
        prepare(s, wsclean_dirty=wsclean_dirty(s))
        fits = psf_fits(s)
        rec["scorer_fit_arcsec"][s] = fits[0] if fits else None
        rec["beam_arcsec_passed"][s] = None if fits else ARCHIVED_S_BEAM
        pair("seen", s, extra_e0=True)
    (O / "beam-s123.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    shutil.rmtree(O / "wsclean" / "tmp", ignore_errors=True)
    (O / "scores").mkdir(exist_ok=True)
    t = f"e{EPS:g}"
    for s in S123:
        score_one(
            s, O / "seen", O / "scores" / f"seen-{s}.json", [f"{s}-default", f"{s}-{t}"]
        )


def c_score():
    (O / "scores").mkdir(exist_ok=True)
    t = f"e{EPS:g}"
    for s in CONFIRM_NEW:
        score_one(
            s, O / "new", O / "scores" / f"new-{s}.json", [f"{s}-default", f"{s}-{t}"]
        )
        jobs = [f"{s}-abs-nominres-fast-j8", f"{s}-abs-nominres-hogbom-j8"]
        score_one(s, O / "wsclean", O / "scores" / f"wsclean-{s}.json", jobs)


# --- table and verdict -------------------------------------------------------


def report(d, name):
    return json.loads((d / f"{name}-report.json").read_text(encoding="utf-8"))


def row(job, rep=None):
    r = rep["run"] if rep else None
    return {
        "name": job["name"],
        "majors": r["major_cycles"] if r else job["log"]["major_iterations"],
        "components": r["components"] if r else job["log"]["components"],
        "false_mjy": job["false_flux_abs"] * 1e3,
        "q_qt": job["q_over_q_truth"],
        "rec_fw": job["recovery_all"]["flux_weighted"],
        "inner_peak_ujy": job["exact_residual_inner_peak_abs"] * 1e6,
        "own_peak_over_t": r["residual_peak_abs"] / T if r else None,
        "cycle_start_over_t": [round(c["peak_start"] / T, 5) for c in r["cycles"]]
        if r
        else None,
        "cycle_components": [c["components"] for c in r["cycles"]] if r else None,
        "seconds_total": r["seconds"]["total"] if r else None,
        "seconds_major": r["seconds"]["major"] if r else None,
        "budget": r["stop"] != "Threshold" if r else None,
        "ascending": r["ascending_major_cycles"] if r else None,
    }


def i2(d_rep, r_rep, thr=T):
    """R is D cut at its first cycle whose start peak is below (1 + EPS) T."""
    cyc = d_rep["run"]["cycles"]
    k = next((c["index"] for c in cyc if c["peak_start"] < (1 + EPS) * thr), len(cyc))
    rc = r_rep["run"]["cycles"]
    return len(rc) == k and [c["components"] for c in rc] == [
        c["components"] for c in cyc[:k]
    ]


def qd(e, d):
    return {
        "false": e["false_mjy"] <= 1.1 * d["false_mjy"],
        "q": abs(e["q_qt"] / d["q_qt"] - 1) <= 0.002,
        "rec": e["rec_fw"] >= d["rec_fw"] - 0.005,
        "own_peak": e["own_peak_over_t"] < 1 + EPS,
        "exact_peak": e["inner_peak_ujy"]
        <= max(d["inner_peak_ujy"], 100.0) + EPS * 100.0,
    }


def qw(x, fast, plain):
    return {
        "false": x["false_mjy"] <= 1.6 * min(fast["false_mjy"], plain["false_mjy"]),
        "q": abs(x["q_qt"] / plain["q_qt"] - 1) <= 0.002,
        "rec": x["rec_fw"] >= plain["rec_fw"] - 0.005,
    }


def wsclean_rows(s):
    f = (O / "scores" if s in NEW else O / "in/scores") / f"wsclean-{s}.json"
    if not f.exists():
        return None, None
    w = json.loads(f.read_text(encoding="utf-8"))["jobs"]
    fast = row(next(j for n, j in w.items() if "-fast-" in n))
    plain = row(next(j for n, j in w.items() if "-hogbom-" in n))
    return fast, plain


def sky_record(stage, s):
    t = f"e{EPS:g}"
    f = O / "scores" / f"{stage}-{s}.json"
    if not f.exists():
        return None
    sc = json.loads(f.read_text(encoding="utf-8"))["jobs"]
    dr, rr = report(O / stage, f"{s}-default"), report(O / stage, f"{s}-{t}")
    d, e = row(sc[f"{s}-default"], dr), row(sc[f"{s}-{t}"], rr)
    rec = {"default": d, "rule": e, "q_d": qd(e, d), "i2": i2(dr, rr)}
    rec["saving"] = d["majors"] - e["majors"]
    fast, plain = wsclean_rows(s)
    if fast is not None:
        rec.update(wsclean_fast=fast, wsclean_plain=plain)
        rec["q_w_rule"], rec["q_w_default"] = qw(e, fast, plain), qw(d, fast, plain)
        rec["below_plain"] = (
            e["majors"] < plain["majors"] and e["false_mjy"] <= plain["false_mjy"]
        )
    return rec


def i1():
    out = {}
    for s in ("s1", "s2", "s3"):
        same = {}
        for k in FITS:
            a = O / "seen" / f"{s}-default-{k}.fits"
            b = O / "seen" / f"{s}-e0-{k}.fits"
            same[k] = (
                a.exists()
                and b.exists()
                and hashlib.sha256(a.read_bytes()).digest()
                == hashlib.sha256(b.read_bytes()).digest()
            )
        out[s] = same
    return out


def pilot_record(n):
    t = f"e{EPS:g}"
    c = json.loads((O / "scores" / f"pilot-compare-{n}.json").read_text())
    d, e = report(O / "pilot", f"{n}-default"), report(O / "pilot", f"{n}-{t}")
    off_d = c["jobs"][f"{n}-default"]["off_source_model_abs_flux"]
    off_e = c["jobs"][f"{n}-{t}"]["off_source_model_abs_flux"]
    agree = c["compact_agreement"][f"{n}-{t}/{n}-default"]
    rec = {
        "majors": [d["run"]["major_cycles"], e["run"]["major_cycles"]],
        "components": [d["run"]["components"], e["run"]["components"]],
        "off_source_abs_jy": [off_d, off_e],
        "off_ratio": off_e / off_d,
        "compact_median": agree["median"],
        "compact_n": agree["n"],
        "budget": d["run"]["stop"] != "Threshold" or e["run"]["stop"] != "Threshold",
        "ascending": d["run"]["ascending_major_cycles"]
        + e["run"]["ascending_major_cycles"],
        "seconds_total": [d["run"]["seconds"]["total"], e["run"]["seconds"]["total"]],
    }
    rec["ok"] = (
        rec["off_ratio"] <= 1.1
        and abs(rec["compact_median"] - 1) <= 0.005
        and not rec["budget"]
        and rec["ascending"] == 0
    )
    thr_jy = float(next(p[1] for p in PILOT if p[2] == n))
    rec["i2"] = i2(d, e, thr_jy)
    return rec


def table():
    out = {"eps": EPS, "i1": i1(), "seen": {}, "new": {}, "pilot": {}}
    if CONFIRM:
        # Amendment 4: S1-S3 from this leg; H1-H8 and the pilot carried from the
        # 2026-11-17 as-run table (before amendment 3).
        asrun = json.loads((PREV / "summary-asrun.json").read_text(encoding="utf-8"))
        out["carried_from"] = str(PREV / "summary-asrun.json")
        out["beam_s123"] = json.loads(
            (O / "beam-s123.json").read_text(encoding="utf-8")
        )
        for s in SEEN:
            out["seen"][s] = sky_record("seen", s) if s in S123 else asrun["seen"][s]
        out["pilot"] = asrun["pilot"]
    else:
        for s in SEEN:
            out["seen"][s] = sky_record("seen", s)
        for _, _, n in PILOT:
            f = O / "scores" / f"pilot-compare-{n}.json"
            out["pilot"][n] = pilot_record(n) if f.exists() else None
    for s in NEW:
        out["new"][s] = sky_record("new", s)

    def ok_sky(r):
        return (
            all(r["q_d"].values())
            and not r["rule"]["budget"]
            and not r["default"]["budget"]
            and r["rule"]["ascending"] == 0
            and r["default"]["ascending"] == 0
        )

    new = out["new"]
    complete = all(r is not None and "q_w_rule" in r for r in new.values())
    i1_ok = all(all(v.values()) for v in out["i1"].values())
    seen_ok = all(r is not None and ok_sky(r) for r in out["seen"].values())
    pilot_ok = all(r is not None and r["ok"] for r in out["pilot"].values())
    i2_ok = all(
        r is not None and r["i2"]
        for r in [*out["seen"].values(), *new.values(), *out["pilot"].values()]
    )
    out["checks"] = {
        "complete": complete,
        "i1": i1_ok,
        "i2": i2_ok,
        "seen": seen_ok,
        "pilot": pilot_ok,
    }
    if complete:
        qd_ok = all(ok_sky(r) for r in new.values())
        qw_ok = all(
            all(v or not r["q_w_default"][k] for k, v in r["q_w_rule"].items())
            for r in new.values()
        )
        sav = [r["saving"] for r in new.values()]
        mean_s = sum(sav) / len(sav)
        n_save = sum(x >= 1 for x in sav)
        out["checks"].update(q_d_new=qd_ok, q_w_new=qw_ok)
        out.update(savings=sav, mean_saving=mean_s, skies_saving=n_save)
        if not (qd_ok and qw_ok and seen_ok and pilot_ok and i1_ok and i2_ok):
            verdict = "not yet"
        elif mean_s >= 1 and n_save >= 4:
            verdict = "switch"
        else:
            verdict = "keep opt-in"
        allsav = sav + [r["saving"] for r in out["seen"].values() if r]
        out.update(
            verdict=verdict,
            at_most_5_new=all(r["rule"]["majors"] <= 5 for r in new.values()),
            pooled_mean_saving=sum(allsav) / len(allsav),
            pooled_n=len(allsav),
            novelty=all(r["below_plain"] for r in new.values()),
            median_seconds_ratio=statistics.median(
                r["rule"]["seconds_total"] / r["default"]["seconds_total"]
                for r in new.values()
            ),
        )
    else:
        out["verdict"] = "not yet (incomplete)"
    (O / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for grp in ("seen", "new"):
        for s, r in out[grp].items():
            if r is None:
                print(grp, s, "missing")
                continue
            d, e = r["default"], r["rule"]
            print(
                f"{grp} {s:<4} D {d['majors']} R {e['majors']} s {r['saving']} "
                f"false {d['false_mjy']:.3f}/{e['false_mjy']:.3f} Q {d['q_qt']:.5f}/{e['q_qt']:.5f} "
                f"rec {d['rec_fw']:.4f}/{e['rec_fw']:.4f} exact {d['inner_peak_ujy']:.2f}/{e['inner_peak_ujy']:.2f} "
                f"own {e['own_peak_over_t']:.4f} QD {all(r['q_d'].values())} I2 {r['i2']}"
                + (
                    f" QW {r['q_w_rule']} QWd {r['q_w_default']} W {r['wsclean_fast']['majors']}/{r['wsclean_plain']['majors']}"
                    if "q_w_rule" in r
                    else ""
                )
            )
    for n, r in out["pilot"].items():
        print("pilot", n, r)
    print("checks", out["checks"])
    print(
        "verdict",
        out["verdict"],
        "mean saving",
        out.get("mean_saving"),
        "skies saving",
        out.get("skies_saving"),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "stage",
        choices=[
            "regen",
            "simulate",
            "seen",
            "new",
            "wsclean",
            "pilot",
            "score",
            "table",
            "c-bin",
            "c-seen",
            "c-simulate",
            "c-new",
            "c-wsclean",
            "c-score",
            "c-table",
        ],
    )
    a = p.parse_args()
    global CONFIRM, NEW
    if a.stage.startswith("c-"):
        if O.resolve() == PREV.resolve():
            raise SystemExit("the confirmation leg needs its own run root O")
        CONFIRM, NEW = True, CONFIRM_NEW
    for sub in ("logs", "scores"):
        (O / sub).mkdir(parents=True, exist_ok=True)
    if a.stage == "c-bin":
        c_bin()
    elif a.stage == "c-seen":
        c_seen()
    elif a.stage == "c-simulate":
        if not all((O / "scores" / f"seen-{s}.json").exists() for s in S123):
            raise SystemExit("S1-S3 not scored: H17-H24 are drawn only after c-seen")
        for s in NEW:
            simulate_one(s, 2048)
    elif a.stage == "c-new":
        for s in NEW:
            prepare(s)
            pair("new", s)
    elif a.stage == "c-wsclean":
        wsclean()
    elif a.stage == "c-score":
        c_score()
    elif a.stage == "c-table":
        table()
    elif a.stage == "regen":
        regen()
    elif a.stage == "simulate":
        for s in NEW:
            simulate_one(s, 2048)
    elif a.stage == "seen":
        for s in SEEN:
            prepare(s)
            pair("seen", s, extra_e0=s in ("s1", "s2", "s3"))
    elif a.stage == "new":
        for s in NEW:
            prepare(s)
            pair("new", s)
    elif a.stage == "wsclean":
        wsclean()
    elif a.stage == "pilot":
        pilot()
    elif a.stage == "score":
        score()
    else:
        table()
    print(
        json.dumps({"stage": a.stage, "finished": time.strftime("%Y-%m-%d %H:%M:%S")})
    )


if __name__ == "__main__":
    main()
