# SPDX-License-Identifier: MIT
"""The xf-gap measurement (research/xf-gap.md section 3) on nash: where does
rang's Xf depart from CASA 6.7.6.14's on the held-out 3C 286 simulation?

    python xf_gap.py gen SET               SET: dev | held | held4 | dev90
    python xf_gap.py psi SET               psi per 3C286-SIM scan -> psi-SET.json
    python xf_gap.py rang SET ARM          ARM: m90 | m90_noavg | gpol8 (noavg, Gpol int)
    python xf_gap.py rangcal SET           rang calibrate only (no apply: H0's MS)
    python xf_gap.py casa SET [gpol8]      CASA's chain (FEED -90), MS kept after setjy
    python xf_gap.py h0 SET                harness against the pipeline
    python xf_gap.py ladder SET AVG        L0-L3 on CASA's model.ms (AVG 0 | 1)
    python xf_gap.py mirror SET            M1-M3 and T0: CASA on rang's tables
    python xf_gap.py gauge SET             one applier, both table sets, 3C286-SIM
    python xf_gap.py score OUT.json        every read of section 3 -> OUT.json

The rang and CASA chains are chi-offset's (research/results/chi-offset/
sim_chi.py, imported unchanged); CASA runs in the apptainer image instead of
docker. Outputs under ~/rang-data/outputs/xf-gap-20261117 (XFGAP_OUT).
"""

import copy
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "chi-offset"))
sys.path.insert(0, str(HERE.parent / "xf-preavg"))
import sim_chi
import xf_preavg

O = Path(os.environ.get("XFGAP_OUT", Path.home() / "rang-data/outputs/xf-gap-20261117"))
SIF = Path.home() / "rang-data" / "oracle-images" / "rang-o-casa_6.7.6.14.sif"
THREADS = int(os.environ.get("XFGAP_THREADS", "2"))
HELD_SEEDS = xf_preavg.HELD_SEEDS
SETS = {
    "dev": (None, 4),
    "held": (HELD_SEEDS, 90),
    "held4": (HELD_SEEDS, 4),
    "dev90": (None, 90),
}
ORDER = ("K", "G", "B", "Gpol", "Kcross", "Xf")
LADDER = {"L3": ORDER[:5], "L2": ORDER[:4], "L1": ORDER[:3], "L0": ()}
MIRROR = {"M1": ORDER[:3], "M2": ORDER[:4], "M3": ORDER[:5]}
GPOL8 = ("solint: 60s, calmode: p", "solint: int, calmode: p")


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(O / "xf_gap.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def src(s):
    return sim_chi.src_ms(O, s)


# -- data ----------------------------------------------------------------------


def gen(s):
    from rang import simtruth as st
    from rang import simtruth_ms

    seeds, xints = SETS[s]
    st.SMALL_LENGTH["X"] = xints
    st.FULL_LENGTH["X"] = xints
    d = O / f"truth-{s}"
    d.mkdir(parents=True, exist_ok=True)
    orig = st.casa_gauge

    def gauge(truth, refant, nu, nu0):
        g = orig(truth, refant, nu, nu0)
        np.savez(d / "gauge.npz", xf=g["xf"], kcross=g["kcross"], freq=nu, nu0=nu0,
                 refant=refant, tau_c_eff_ns=g["tau_c_eff_ns_from_k"])  # fmt: skip
        return g

    st.casa_gauge = gauge
    argv = ["generate", "poldx", str(d), "--noiseless", "--workers", str(THREADS)]
    if seeds:
        argv += ["--seeds", seeds]
    t0 = time.perf_counter()
    simtruth_ms.main(argv)
    log(f"gen {s} seeds={seeds} xints={xints} {time.perf_counter() - t0:.1f}s")


def psi(s):
    xf_preavg.psi(O, s, O / f"psi-{s}.json")


# -- rang arms -----------------------------------------------------------------


def rang(s, arm):
    if arm == "gpol8":
        sim_chi.CONFIG = sim_chi.CONFIG.replace(*GPOL8)
        sim_chi.RANG_ARMS["gpol8"] = {
            "far": "-90",
            "gpol_parang": "true",
            "avg": "false",
        }
    t0 = time.perf_counter()
    rc = sim_chi.rang_arm(O, s, arm)
    log(f"rang {s} {arm} rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


def rangcal(s):
    """rang's calibrate stage alone on a fresh copy (MODEL_DATA rang's, FLAG
    as the solves saw it): the MS of the harness control H0."""
    d = O / f"rangcal-{s}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    shutil.copytree(src(s), d / "sim.ms")
    a = sim_chi.RANG_ARMS["m90_noavg"]
    (d / "config.yaml").write_text(sim_chi.CONFIG.format(
        scans="", uv=sim_chi.UVRANGE, far=a["far"], gpol_parang=a["gpol_parang"],
        avg="false", stages="calibrate"), encoding="utf-8")  # fmt: skip
    t0 = time.perf_counter()
    with open(d / "rang.log", "w", encoding="utf-8") as fh:
        rc = subprocess.run([sim_chi.RANG_CORE, "run", str(d / "config.yaml"),
                             str(d / "sim.ms")], stdout=fh, stderr=subprocess.STDOUT,
                            check=False).returncode  # fmt: skip
    log(f"rangcal {s} rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


def rang_tables(d):
    return Path(d) / "sim.ms.rang-run" / "calibrate"


# -- CASA (apptainer) ----------------------------------------------------------


def apptainer(d, steps, label):
    (d / "set_feed.py").write_text(sim_chi.SET_FEED, encoding="utf-8")
    script = " && ".join(steps)
    cmd = ["apptainer", "exec", "--containall", "--env", "HOME=/tmp", "--env",
           f"OMP_NUM_THREADS={THREADS}", "--pwd", "/tmp", "--bind", f"{d}:/r",
           "--bind", f"{ROOT / 'examples'}:/ex:ro", str(SIF), "sh", "-c", script]  # fmt: skip
    t0 = time.perf_counter()
    with open(d / "casa.out", "w", encoding="utf-8") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                            check=False).returncode  # fmt: skip
    errs = []
    res = d / "tasks.json"
    if res.exists():
        errs = [r["error"] for r in json.loads(res.read_text()) if r["error"]]
    log(f"casa {label} rc={rc} errors={len(errs)} {time.perf_counter() - t0:.1f}s")
    return 1 if errs else rc


SET_FEED = "/opt/casa/bin/python -I /r/set_feed.py /r/sim.ms -1.5707963267948966"
TASKS = "/opt/casa/bin/python -I /ex/oracle_pol.py tasks /r/spec.json /r/tasks.json"


def _calls(gpol8=False):
    calls = sim_chi.casa_calls("/r/sim.ms", "/r/tables")
    # The MS as the solves see it (after setjy, before any applycal flag).
    calls.insert(
        2, {"task": "copytree", "args": {"src": "/r/sim.ms", "dst": "/r/model.ms"}}
    )
    if gpol8:
        for c in calls:
            if c["args"].get("caltable") == "/r/tables/Gpol":
                c["args"]["solint"] = "int"
    return calls


def casa(s, variant=""):
    d = O / f"casa-{s}-m90{'-' + variant if variant else ''}"
    if d.exists():
        shutil.rmtree(d)
    (d / "tables").mkdir(parents=True)
    shutil.copytree(src(s), d / "sim.ms")
    (d / "spec.json").write_text(json.dumps(_calls(variant == "gpol8"), indent=1))
    rc = apptainer(d, [SET_FEED, TASKS], f"{s} m90 {variant}")
    if rc == 0:
        sim_chi.score(d / "sim.ms", "CORRECTED_DATA", "FLAG", d)
    return rc


def mirror(s):
    """M1-M3: CASA's later solves on rang's earlier tables (the m90_noavg
    arm's), CASA's setjy, a fresh copy. T0: CASA's Xf on CASA's own K..Kcross
    passed through rang's reader and writer."""
    from rang.formats import caltable

    rt = rang_tables(O / f"rang-{s}-m90_noavg")
    ct = O / f"casa-{s}-m90" / "tables"
    rcs = {}
    for name, given in list(MIRROR.items()) + [("T0", ORDER[:5])]:
        d = O / f"mirror-{s}-{name}"
        if d.exists():
            shutil.rmtree(d)
        (d / "tables").mkdir(parents=True)
        for t in given:
            if name == "T0":
                caltable.write(caltable.read(ct / t), d / "tables" / t)
            else:
                shutil.copytree(rt / t, d / "tables" / t)
        shutil.copytree(src(s), d / "sim.ms")
        calls = [c for c in sim_chi.casa_calls("/r/sim.ms", "/r/tables")
                 if c["task"] == "setjy"
                 or (c["args"].get("caltable", "").rsplit("/", 1)[-1] in ORDER
                     and c["args"]["caltable"].rsplit("/", 1)[-1] not in given)]  # fmt: skip
        (d / "spec.json").write_text(json.dumps(calls, indent=1))
        rcs[name] = apptainer(d, [SET_FEED, TASKS], f"{s} mirror {name}")
        shutil.rmtree(d / "sim.ms")
    return max(rcs.values())


# -- the harness: rang's solvers as the pipeline calls them --------------------


def _pipeline_terms(cfg, ms):
    from rang import cal_refant, core_chunks, core_config, core_pipeline

    raw = core_config.load(cfg)
    config = core_config.validate(raw, ["calibrate"], source=Path(cfg))
    config, _ = cal_refant.resolve_config(config, ms)
    info = core_pipeline.inspect_ms(ms)
    terms = core_pipeline.chain_terms(config, info, Path(cfg))
    plan = core_chunks.budget(config, info)
    weight = core_pipeline.chain_weight_column(config, info)
    return [t for t in terms if t["name"] in ORDER], plan, weight


def harness(ms, cfg, given_dir, given, out, average_time=False):
    """Solve the chain's K..Xf on `ms` (model in MODEL_DATA) as
    `cal_chain.run` does, with the tables named in `given` read from
    `given_dir` instead of solved. Writes the solved tables to `out`."""
    from rang import cal_chain
    from rang.formats import caltable

    terms, plan, weight = _pipeline_terms(cfg, ms)
    common = {"model_column": "MODEL_DATA", "weight_column": weight,
              "budget": plan.chain()}  # fmt: skip
    if average_time:
        common["average_time"] = True
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tables, record = {}, {}
    for term in terms:
        name = term["name"]
        if name in given:
            tables[name] = {
                "table": caltable.read(Path(given_dir) / name),
                "type": term["type"],
            }
            record[name] = "given"
            continue
        (f,) = term["fields"]
        if term["type"] in ("K", "G", "B"):
            table, _, _ = cal_chain._solve_one(ms, term, f, tables, dict(common))
        else:
            table, rec = cal_chain._solve_pol(ms, term, f, tables, dict(common))
            record[name] = rec
        tables[name] = {"table": table, "type": term["type"]}
        caltable.write(table, out / name)
    (out / "harness.json").write_text(json.dumps(record, indent=1, default=str) + "\n")
    return tables


def h0(s):
    """The harness reproduces the pipeline: (a) every term solved on the
    calibrate-only MS; (b) Xf alone on rang's own K..Kcross read back."""
    d = O / f"rangcal-{s}"
    ms, cfg, rt = d / "sim.ms", d / "config.yaml", rang_tables(d)
    t0 = time.perf_counter()
    harness(ms, cfg, rt, (), O / f"h0a-{s}")
    harness(ms, cfg, rt, ORDER[:5], O / f"h0b-{s}")
    log(f"h0 {s} {time.perf_counter() - t0:.1f}s")


def ladder(s, avg):
    """L0-L3 on CASA's model.ms; rang's config from the m90 (avg) or
    m90_noavg arm (they differ in average_time only)."""
    avg = bool(int(avg))
    arm = "m90" if avg else "m90_noavg"
    ms = O / f"casa-{s}-m90" / "model.ms"
    cfg = O / f"rang-{s}-{arm}" / "config.yaml"
    ct = O / f"casa-{s}-m90" / "tables"
    for name, given in LADDER.items():
        t0 = time.perf_counter()
        harness(ms, cfg, ct, given, O / f"ladder-{s}-{arm}-{name}", average_time=avg)
        log(f"ladder {s} {arm} {name} {time.perf_counter() - t0:.1f}s")


def gauge(s):
    """K, G, B, Gpol, Kcross, Xf of each side applied by rang's applier (no
    parang, calflag) to 3C286-SIM's DATA on copies of CASA's model.ms."""
    from rang import applycal

    sides = {"rang": rang_tables(O / f"rang-{s}-m90_noavg"),
             "casa": O / f"casa-{s}-m90" / "tables"}  # fmt: skip
    for side, td in sides.items():
        d = O / f"gauge-{s}-{side}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        shutil.copytree(O / f"casa-{s}-m90" / "model.ms", d / "sim.ms")
        t0 = time.perf_counter()
        applycal.applycal(d / "sim.ms", [str(td / t) for t in ORDER],
                          interp=["linear"] * 4 + ["nearest"] * 2,
                          field=[sim_chi.XCAL], applymode="calflag")  # fmt: skip
        log(f"gauge {s} {side} {time.perf_counter() - t0:.1f}s")


# -- reads ---------------------------------------------------------------------


def xf_of(path):
    """Xf per channel (row 0; the reader checks every row holds it)."""
    c, f = xf_preavg._xf(path)
    x, fl = c[..., 0], f[..., 0]
    ok = ~fl
    spread = (
        np.abs(np.angle(x[:, :] / x[:1, :]))[ok & ok[:1]].max() if len(x) > 1 else 0.0
    )
    return x[0], fl[0], float(np.degrees(spread))


def delta(a, b, freq=None):
    """Signed arg(a / b) per channel (deg); NaN where either is flagged."""
    (xa, fa, _), (xb, fb, _) = a, b
    d = np.degrees(np.angle(xa / xb))
    d[fa | fb] = np.nan
    return d


def summary(d, freq, nu0):
    ok = np.isfinite(d)
    out = {"n": int(ok.sum()), "median_abs": float(np.median(np.abs(d[ok]))),
           "max_abs": float(np.max(np.abs(d[ok]))), "mean": float(np.mean(d[ok]))}  # fmt: skip
    x = (freq[ok] - nu0) / 1e9
    A = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(A, d[ok], rcond=None)
    res = d[ok] - A @ coef
    out.update(fit_const_deg=float(coef[0]), fit_slope_deg_per_ghz=float(coef[1]),
               slope_as_dtau_ns=float(coef[1] / 360.0),
               fit_rms_resid_deg=float(np.sqrt(np.mean(res**2))))  # fmt: skip
    return out


def shares(parts, total):
    ok = np.isfinite(total)
    for p in parts.values():
        ok &= np.isfinite(p)
    den = float(np.sum(total[ok] ** 2))
    return {k: float(np.sum(v[ok] * total[ok]) / den) for k, v in parts.items()}


def _gains(path):
    from rang.formats import caltable

    t = caltable.read(path)
    m = t.main
    key = "FPARAM" if "FPARAM" in m and m["FPARAM"] is not None else "CPARAM"
    v = np.array([np.asarray(x) for x in m[key]])
    f = np.array([np.asarray(x) for x in m["FLAG"]])
    return {"time": np.asarray(m["TIME"], float), "ant": np.asarray(m["ANTENNA1"]),
            "v": v, "f": f}  # fmt: skip


def cmp_gpol(a, b):
    ga, gb = _gains(a), _gains(b)
    ta, tb = np.unique(ga["time"]), np.unique(gb["time"])
    out = {"n_times": [len(ta), len(tb)]}
    if len(ta) != len(tb) or len(ga["v"]) != len(gb["v"]):
        out["same_grid"] = False
        return out
    out["same_grid"] = True
    out["max_time_diff_s"] = float(np.max(np.abs(ta - tb)))
    ok = ~ga["f"] & ~gb["f"]
    ph = np.degrees(np.angle(ga["v"] / gb["v"]))
    ph[~ok] = np.nan
    out["phase_diff_deg"] = {"median_abs": float(np.nanmedian(np.abs(ph))),
                             "max_abs": float(np.nanmax(np.abs(ph)))}  # fmt: skip
    # X-Y part per row, its mean over antennas per time (what Xf can absorb).
    xy = ph[:, 0, 0] - ph[:, 0, 1]
    per_t = [float(np.nanmean(xy[ga["time"] == t])) for t in ta]
    out["xy_diff_deg"] = {"median_abs": float(np.nanmedian(np.abs(xy))),
                          "max_abs": float(np.nanmax(np.abs(xy))),
                          "mean_over_ants_per_time": per_t}  # fmt: skip
    out["flag_diff"] = int((ga["f"] != gb["f"]).sum())
    return out


def cmp_kcross(a, b):
    ga, gb = _gains(a), _gains(b)
    r = []
    for t in np.unique(ga["time"]):
        ia = np.flatnonzero(ga["time"] == t)[0]
        jb = np.argmin(np.abs(gb["time"] - t))
        r.append({"time": float(t), "dt_s": float(gb["time"][jb] - t),
                  "tau_a_ns": float(ga["v"][ia, 0, 0]), "tau_b_ns": float(gb["v"][jb, 0, 0]),
                  "dtau_ns": float(ga["v"][ia, 0, 0] - gb["v"][jb, 0, 0])})  # fmt: skip
    return r


def gauge_read(s):
    from rang import core_ms

    out = {}
    v = {}
    for side in ("rang", "casa"):
        ms = O / f"gauge-{s}-{side}" / "sim.ms"
        if not ms.exists():
            return None
        with core_ms.open_table(ms / "FIELD") as t:
            fid = [str(n) for n in t.getcol("NAME")].index(sim_chi.XCAL)
        with core_ms.open_table(ms) as t:
            rows = np.flatnonzero(np.asarray(t.getcol("FIELD_ID")) == fid)
            v[side] = np.asarray(t.getcol("CORRECTED_DATA"))[rows]
            fl = np.asarray(t.getcol("FLAG"))[rows]
            v[side + "_flag"] = fl
    ok = ~(v["rang_flag"] | v["casa_flag"])
    z = np.where(ok, v["rang"] * np.conj(v["casa"]), 0).sum(axis=0)  # (chan, corr)
    for i, c in enumerate(("XX", "XY", "YX", "YY")):
        ph = np.degrees(np.angle(z[:, i]))
        good = np.abs(z[:, i]) > 0
        out[c] = {"median_abs": float(np.median(np.abs(ph[good]))),
                  "max_abs": float(np.max(np.abs(ph[good])))}  # fmt: skip
    return out


def _freq(s):
    from rang import core_ms

    with core_ms.open_table(src(s) / "SPECTRAL_WINDOW") as t:
        return np.asarray(t.getcol("CHAN_FREQ"))[0]


def score(dest):
    res = {"sets": {}}
    for s in SETS:
        rn, ra, cas = (
            O / f"rang-{s}-m90_noavg",
            O / f"rang-{s}-m90",
            O / f"casa-{s}-m90",
        )
        if not (cas / "tables" / "Xf").exists() or not (rn / "chi.json").exists():
            continue
        freq = _freq(s)
        g = np.load(O / f"truth-{s}" / "gauge.npz")
        nu0 = float(g["nu0"])
        truth = (np.asarray(g["xf"]), np.zeros(len(freq), bool), 0.0)
        X = {"R": xf_of(rang_tables(rn) / "Xf"), "A": xf_of(rang_tables(ra) / "Xf"),
             "CASA": xf_of(cas / "tables" / "Xf")}  # fmt: skip
        r = {"xf_row_spread_deg": {k: v[2] for k, v in X.items()}}
        for k in ("R", "A"):
            r[f"{k}_vs_CASA"] = summary(delta(X[k], X["CASA"]), freq, nu0)
        for k in ("R", "A", "CASA"):
            r[f"{k}_vs_truth"] = summary(delta(X[k], truth), freq, nu0)
        ca, cc = xf_preavg._chi(ra), xf_preavg._chi(cas)
        r["max_chi_avg_minus_casa"] = max(
            abs(ca[k]["chi_deg"] - cc[k]["chi_deg"]) for k in ca
        )
        r["chi"] = {int(k): [ca[k]["chi_deg"], cc[k]["chi_deg"]] for k in ca}
        p = O / f"psi-{s}.json"
        if p.exists():
            r["psi"] = [
                (x["scan"], x["span_deg"]) for x in json.loads(p.read_text())["scans"]
            ]
        # H0
        h = {}
        for tag in ("h0a", "h0b"):
            hd = O / f"{tag}-{s}"
            if (hd / "Xf").exists():
                rt = rang_tables(O / f"rangcal-{s}")
                h[tag] = {"Xf_max_abs_deg": summary(delta(xf_of(hd / "Xf"), xf_of(rt / "Xf")),
                                                    freq, nu0)["max_abs"]}  # fmt: skip
                if tag == "h0a":
                    h[tag]["Gpol"] = cmp_gpol(hd / "Gpol", rt / "Gpol")
                    h[tag]["Kcross"] = cmp_kcross(hd / "Kcross", rt / "Kcross")
                h[tag]["rangcal_vs_arm_Xf_max_abs_deg"] = summary(
                    delta(xf_of(rt / "Xf"), X["R"]), freq, nu0)["max_abs"]  # fmt: skip
        r["H0"] = h
        # Ladder
        for arm, key in (("m90_noavg", "R"), ("m90", "A")):
            L = {}
            for name in LADDER:
                p = O / f"ladder-{s}-{arm}-{name}" / "Xf"
                if p.exists():
                    L[name] = xf_of(p)
            if len(L) < 4:
                continue
            parts = {
                "model (R-L0)": delta(X[key], L["L0"]),
                "KGB (L0-L1)": delta(L["L0"], L["L1"]),
                "Gpol (L1-L2)": delta(L["L1"], L["L2"]),
                "Kcross (L2-L3)": delta(L["L2"], L["L3"]),
                "Xf solver and P (L3-CASA)": delta(L["L3"], X["CASA"]),
            }
            total = delta(X[key], X["CASA"])
            lr = {"shares": shares(parts, total),
                  "parts": {k: summary(v, freq, nu0) for k, v in parts.items()},
                  "sum_check_max_abs_deg": float(np.nanmax(np.abs(
                      sum(parts.values()) - total)))}  # fmt: skip
            ct = cas / "tables"
            lr["Gpol_L1_vs_CASA"] = cmp_gpol(
                O / f"ladder-{s}-{arm}-L1" / "Gpol", ct / "Gpol"
            )
            lr["Kcross_L2_vs_CASA"] = cmp_kcross(O / f"ladder-{s}-{arm}-L2" / "Kcross",
                                                 ct / "Kcross")  # fmt: skip
            lr["Kcross_R_vs_CASA"] = cmp_kcross(rang_tables(rn if key == "R" else ra) / "Kcross",
                                                ct / "Kcross")  # fmt: skip
            lr["Gpol_R_vs_CASA"] = cmp_gpol(rang_tables(rn if key == "R" else ra) / "Gpol",
                                            ct / "Gpol")  # fmt: skip
            r[f"ladder_{arm}"] = lr
        # Mirror and T0
        M = {}
        for name in list(MIRROR) + ["T0"]:
            p = O / f"mirror-{s}-{name}" / "tables" / "Xf"
            if p.exists():
                M[name] = xf_of(p)
        if "T0" in M:
            r["T0_max_abs_deg"] = summary(delta(M["T0"], X["CASA"]), freq, nu0)[
                "max_abs"
            ]
        if len(MIRROR.keys() & M.keys()) == 3:
            total = delta(X["R"], X["CASA"])
            parts = {
                "Xf solver (R-M3)": delta(X["R"], M["M3"]),
                "Kcross (M3-M2)": delta(M["M3"], M["M2"]),
                "Gpol (M2-M1)": delta(M["M2"], M["M1"]),
                "KGB and model (M1-CASA)": delta(M["M1"], X["CASA"]),
            }
            r["mirror"] = {"shares": shares(parts, total),
                           "parts": {k: summary(v, freq, nu0) for k, v in parts.items()}}  # fmt: skip
        gr = gauge_read(s)
        if gr:
            r["gauge"] = gr
        # gpol8
        r8, c8 = O / f"rang-{s}-gpol8", O / f"casa-{s}-m90-gpol8"
        if (r8 / "chi.json").exists() and (c8 / "tables" / "Xf").exists():
            x8r, x8c = xf_of(rang_tables(r8) / "Xf"), xf_of(c8 / "tables" / "Xf")
            r["gpol8"] = {"R_vs_CASA": summary(delta(x8r, x8c), freq, nu0),
                          "R8_vs_R": summary(delta(x8r, X["R"]), freq, nu0),
                          "CASA8_vs_CASA": summary(delta(x8c, X["CASA"]), freq, nu0),
                          "Gpol": cmp_gpol(rang_tables(r8) / "Gpol", c8 / "tables" / "Gpol")}  # fmt: skip
        # Model
        r["model"] = model_diff(s)
        res["sets"][s] = r
    Path(dest).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


def model_diff(s):
    from rang import core_ms

    a, b = O / f"rangcal-{s}" / "sim.ms", O / f"casa-{s}-m90" / "model.ms"
    if not (a.exists() and b.exists()):
        return None
    out = {}
    for fname in (sim_chi.XCAL, sim_chi.FCAL):
        with core_ms.open_table(a / "FIELD") as t:
            fid = [str(n) for n in t.getcol("NAME")].index(fname)
        m = {}
        for k, ms in (("rang", a), ("casa", b)):
            with core_ms.open_table(ms) as t:
                rows = np.flatnonzero(np.asarray(t.getcol("FIELD_ID")) == fid)
                m[k] = np.asarray(t.getcol("MODEL_DATA"))[rows]
        den = np.maximum(np.abs(m["casa"][..., [0]]), 1e-30)
        out[fname] = {
            "max_rel_diff": float(np.max(np.abs(m["rang"] - m["casa"]) / den))
        }
    return out


# -- post hoc (research/xf-gap.md section 6) ------------------------------------


def _take(table, idx):
    t = copy.deepcopy(table)
    for k, v in t.main.items():
        if v is None:
            continue
        t.main[k] = v[idx] if isinstance(v, np.ndarray) else [v[i] for i in idx]
    return t


def _missing(rang_gpol, casa_gpol):
    """rang's row mask: True where CASA has no solution within 1 s."""
    tc = np.unique(np.asarray(casa_gpol.main["TIME"], float))
    tr = np.asarray(rang_gpol.main["TIME"], float)
    return np.array([np.min(np.abs(tc - t)) > 1.0 for t in tr])


def p1(s):
    """L2f: rang's Kcross and Xf on CASA's K, G, B and CASA's Gpol completed
    by the ladder L1's (rang's, on CASA's K, G, B) rows where CASA has none."""
    from rang.formats import caltable

    ct = O / f"casa-{s}-m90" / "tables"
    cg = caltable.read(ct / "Gpol")
    rg = caltable.read(O / f"ladder-{s}-m90_noavg-L1" / "Gpol")
    miss = np.flatnonzero(_missing(rg, cg))
    merged = copy.deepcopy(cg)
    for k in merged.main:
        a, b = cg.main[k], rg.main[k]
        if a is None:
            continue
        if isinstance(a, np.ndarray):
            merged.main[k] = np.concatenate([a, np.asarray(b)[miss]])
        else:
            merged.main[k] = list(a) + [b[i] for i in miss]
    order = np.lexsort(
        (np.asarray(merged.main["ANTENNA1"]), np.asarray(merged.main["TIME"]))
    )
    merged = _take(merged, order)
    g = O / f"p1-{s}-given"
    if g.exists():
        shutil.rmtree(g)
    g.mkdir(parents=True)
    for t in ("K", "G", "B"):
        shutil.copytree(ct / t, g / t)
    caltable.write(merged, g / "Gpol")
    ms = O / f"casa-{s}-m90" / "model.ms"
    cfg = O / f"rang-{s}-m90_noavg" / "config.yaml"
    harness(ms, cfg, g, ORDER[:4], O / f"p1-{s}-L2f")
    log(f"p1 {s}: {len(miss)} rows filled from L1")


def p2(s):
    """R-drop: rang's chain on its own MS with rang's Gpol rows removed where
    CASA has none, Kcross and Xf re-solved."""
    from rang.formats import caltable

    d = O / f"rangcal-{s}"
    rt = rang_tables(d)
    rg = caltable.read(rt / "Gpol")
    cg = caltable.read(O / f"casa-{s}-m90" / "tables" / "Gpol")
    keep = np.flatnonzero(~_missing(rg, cg))
    g = O / f"p2-{s}-given"
    if g.exists():
        shutil.rmtree(g)
    g.mkdir(parents=True)
    for t in ("K", "G", "B"):
        shutil.copytree(rt / t, g / t)
    caltable.write(_take(rg, keep), g / "Gpol")
    harness(d / "sim.ms", d / "config.yaml", g, ORDER[:4], O / f"p2-{s}-Rdrop")
    log(f"p2 {s}: {len(rg.main['TIME']) - len(keep)} rows removed")


def posthoc(dest):
    res = {}
    for s in SETS:
        p = O / f"truth-{s}" / "gauge.npz"
        if not p.exists():
            continue
        f, nu0 = _freq(s), float(np.load(p)["nu0"])
        C = xf_of(O / f"casa-{s}-m90" / "tables" / "Xf")
        r = {}
        if (O / f"p1-{s}-L2f" / "Xf").exists():
            L2f = xf_of(O / f"p1-{s}-L2f" / "Xf")
            L1 = xf_of(O / f"ladder-{s}-m90_noavg-L1" / "Xf")
            L2 = xf_of(O / f"ladder-{s}-m90_noavg-L2" / "Xf")
            r["P1_L2f_vs_L1"] = summary(delta(L2f, L1), f, nu0)
            r["P1_L2_vs_L1"] = summary(delta(L2, L1), f, nu0)
            r["P1_L2f_vs_CASA"] = summary(delta(L2f, C), f, nu0)
        if (O / f"p2-{s}-Rdrop" / "Xf").exists():
            rd = xf_of(O / f"p2-{s}-Rdrop" / "Xf")
            r["P2_Rdrop_vs_CASA"] = summary(delta(rd, C), f, nu0)
            rr = xf_of(rang_tables(O / f"rangcal-{s}") / "Xf")
            r["P2_Rdrop_vs_R"] = summary(delta(rd, rr), f, nu0)
        if r:
            res[s] = r
    Path(dest).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


def main(argv):
    O.mkdir(parents=True, exist_ok=True)
    cmd, args = argv[0], argv[1:]
    fn = {"gen": gen, "psi": psi, "rang": rang, "rangcal": rangcal, "casa": casa,
          "h0": h0, "ladder": ladder, "mirror": mirror, "gauge": gauge,
          "score": score, "p1": p1, "p2": p2, "posthoc": posthoc}.get(cmd)  # fmt: skip
    if fn is None:
        raise SystemExit(__doc__)
    rc = fn(*args)
    return rc if isinstance(rc, int) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
