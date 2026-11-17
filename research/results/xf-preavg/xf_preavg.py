"""The xf-preavg measurement (research/xf-preavg.md section 3): does xf-avg-fix's
pre-averaging rule (rang.cal_chunks.psi_groups: one scan, at most 5 deg of
psi per averaged row) hold on a held-out simulation with 3C286-SIM scans
wider than 5 deg of psi, against rang unaveraged and CASA 6.7.6.14's polcal
(its default preavg)?

    python xf_preavg.py gen OUT                   held-out truth -> OUT/truth-held
    python xf_preavg.py copydev OUT SRC           chi-offset's control truth -> OUT/truth-control
    python xf_preavg.py psi OUT TRUTH OUT.json    psi span per 3C286-SIM scan and the
                                                  averaging groups of the Xf solve
    python xf_preavg.py rang OUT TRUTH ARM        ARM: m90 (average_time) | m90_noavg
    python xf_preavg.py casa OUT TRUTH            CASA's chain (FEED -90 written)
    python xf_preavg.py casadefaults OUT          polcal's signature in the container
    python xf_preavg.py score OUT RESULT.json     the gates of section 3
    python xf_preavg.py casa_preavg OUT TRUTH S   post hoc: CASA with polcal preavg S
    python xf_preavg.py posthoc OUT RESULT.json   post hoc: every CASA arm's Xf vs rang

The rang and CASA arms are chi-offset's (research/results/chi-offset/sim_chi.py,
imported unchanged): E2-B's polcal chain, `feed_angle_rotation: -90`.
"""

import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "chi-offset"))
import sim_chi

# Frozen in research/xf-preavg.md section 3 (before any run).
HELD_SEEDS = "20261751,20261752,20261753,20261754"
HELD_X_INTS = 90  # 3C286-SIM scans of 90 x 8 s = 720 s
TOL_CHI_DEG = 0.05  # chi per scan: averaged vs unaveraged rang, and vs CASA
TOL_XF_MEDIAN_DEG = 0.05  # Xf per channel, median
TOL_XF_MAX_DEG = 0.25  # Xf per channel, max
TOL_TRUTH_DEG = 1.11  # |chi - 33| (C6w's tolerance)
TOL_DEV_REPRO_DEG = 0.001  # dev arm against xf-avg-fix's gate1.json


def log(out, msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(Path(out) / "xf_preavg.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def gen(out):
    """poldx's noiseless twin, control truth (FEED -90, a = psi - 90 deg), fresh
    seeds and 720 s 3C286-SIM scans (the later scans start later: new psi)."""
    from rang import simtruth as st
    from rang import simtruth_ms

    st.SMALL_LENGTH["X"] = HELD_X_INTS
    st.FULL_LENGTH["X"] = HELD_X_INTS
    d = Path(out) / "truth-held"
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    simtruth_ms.main(["generate", "poldx", str(d), "--noiseless", "--workers", "4",
                      "--seeds", HELD_SEEDS])  # fmt: skip
    log(out, f"gen held {time.perf_counter() - t0:.1f}s")


def copydev(out, src):
    dst = Path(out) / "truth-control"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(Path(src), dst)
    log(out, f"copied {src} -> {dst}")


def psi(out, truth, dest):
    """ψ per 3C286-SIM scan (antenna 0, CASA frame, as the solve's angle table)
    and the number of averaging groups `psi_groups` forms for the Xf solve
    (solint inf, combine scan: one interval)."""
    from rang import cal_chunks, cal_pol, core_ms

    ms = sim_chi.src_ms(out, truth)
    with core_ms.open_table(ms / "FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(sim_chi.XCAL)
    with core_ms.open_table(ms) as t:
        f = np.asarray(t.getcol("FIELD_ID"))
        rows = np.flatnonzero(f == fid)
        tm = np.asarray(t.getcol("TIME"))[rows]
        sc = np.asarray(t.getcol("SCAN_NUMBER"))[rows]
        a1 = np.asarray(t.getcol("ANTENNA1"))[rows]
        a2 = np.asarray(t.getcol("ANTENNA2"))[rows]
    table = cal_pol.angle_table(ms, tm, a1, a2, fid, "casa", math.radians(-90.0))
    q = cal_pol.table_angles(table, tm, a1, a2)[0]
    groups = cal_chunks.psi_groups(np.zeros(len(rows), np.int64), sc, q)
    res = {"truth": truth, "scans": []}
    for s in np.unique(sc):
        m = sc == s
        p = np.degrees(np.unwrap(q[m][np.argsort(tm[m], kind="stable")]))
        res["scans"].append({
            "scan": int(s), "n_int": len(np.unique(tm[m])),
            "psi_first_deg": float(p[0]), "psi_last_deg": float(p[-1]),
            "span_deg": float(p.max() - p.min()),
            "groups": 1 if groups is None else len(np.unique(groups[m])),
        })  # fmt: skip
    res["groups_total"] = 1 if groups is None else len(np.unique(groups))
    Path(dest).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


def rang(out, truth, arm):
    t0 = time.perf_counter()
    rc = sim_chi.rang_arm(out, truth, arm)
    log(out, f"rang {truth} {arm} rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


def casa(out, truth):
    t0 = time.perf_counter()
    rc = sim_chi.casa_arm(out, truth, "m90")
    log(out, f"casa {truth} m90 rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


def casa_preavg(out, truth, preavg):
    """Post hoc (research/xf-preavg.md section 5): CASA's chain with polcal's
    `preavg` set for Xf and Df (CASA's default is 300 s)."""
    d = Path(out) / f"casa-{truth}-m90-preavg{preavg:g}"
    if d.exists():
        shutil.rmtree(d)
    (d / "tables").mkdir(parents=True)
    shutil.copytree(sim_chi.src_ms(out, truth), d / "sim.ms")
    calls = sim_chi.casa_calls("/r/sim.ms", "/r/tables")
    for c in calls:
        if c["task"] == "polcal":
            c["args"]["preavg"] = float(preavg)
    (d / "spec.json").write_text(json.dumps(calls, indent=1))
    t0 = time.perf_counter()
    rc = sim_chi.casa_docker(d, -math.pi / 2)
    log(
        out,
        f"casa {truth} m90 preavg {preavg:g} rc={rc} {time.perf_counter() - t0:.1f}s",
    )
    if rc == 0:
        sim_chi.score(d / "sim.ms", "CORRECTED_DATA", "FLAG", d)
    return rc


def posthoc(out, dest):
    """Post hoc: the held-out Xf and chi of every CASA preavg arm against rang's
    averaged and unaveraged arms."""
    out = Path(out)
    res = {}
    for truth in ("control", "held"):
        avg, noavg = out / f"rang-{truth}-m90", out / f"rang-{truth}-m90_noavg"
        xa = _xf(avg / "sim.ms.rang-run" / "calibrate" / "Xf")
        xn = _xf(noavg / "sim.ms.rang-run" / "calibrate" / "Xf")
        ca, cn = _chi(avg), _chi(noavg)
        for d in sorted(out.glob(f"casa-{truth}-m90*")):
            if not (d / "chi.json").exists():
                continue
            xc, cc = _xf(d / "tables" / "Xf"), _chi(d)
            res[d.name] = {
                "xf_vs_avg_deg": _xf_diff(xa, xc),
                "xf_vs_noavg_deg": _xf_diff(xn, xc),
                "max_chi_vs_avg": max(
                    abs(cc[s]["chi_deg"] - ca[s]["chi_deg"]) for s in ca
                ),
                "max_chi_vs_noavg": max(
                    abs(cc[s]["chi_deg"] - cn[s]["chi_deg"]) for s in cn
                ),
                "chi": {int(s): cc[s]["chi_deg"] for s in cc},
            }
    Path(dest).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


SIGNATURE = (
    "import inspect; from casatasks import polcal; "
    "print({k: v.default for k, v in inspect.signature(polcal).parameters.items()})"
)


def casadefaults(out):
    inner = " ".join(["docker", "run", "--rm", "--network", "none", "--tmpfs", "/tmp",
                      "-e", "HOME=/tmp", sim_chi.CASA_IMAGE, "/opt/casa/bin/python",
                      "-I", "-c", f"'{SIGNATURE}'"])  # fmt: skip
    r = subprocess.run(["wsl", "-e", "bash", "-lc", inner], capture_output=True,
                       text=True, check=False)  # fmt: skip
    (Path(out) / "casa-polcal-defaults.txt").write_text(r.stdout + r.stderr)
    print(r.stdout[-2000:], r.stderr[-2000:])
    return r.returncode


def _chi(d):
    return {r["scan"]: r for r in json.loads((Path(d) / "chi.json").read_text())}


def _xf(path):
    from rang.formats import caltable

    t = caltable.read(path)
    c = np.array([np.asarray(v) for v in t.main["CPARAM"]])
    f = np.array([np.asarray(v) for v in t.main["FLAG"]])
    return c, f


def _xf_diff(a, b):
    (ca, fa), (cb, fb) = a, b
    # Xf has one value per channel and polarisation; every antenna's row holds it.
    ok = ~fa & ~fb
    d = np.degrees(np.abs(np.angle(ca[ok] / cb[ok])))
    return {"median": float(np.median(d)), "max": float(d.max()), "n": int(ok.sum())}


def _ok(chi, xf):
    return bool(chi <= TOL_CHI_DEG and xf["median"] <= TOL_XF_MEDIAN_DEG
                and xf["max"] <= TOL_XF_MAX_DEG)  # fmt: skip


def score(out, dest):
    out = Path(out)
    res = {"tolerances_deg": {"chi": TOL_CHI_DEG, "xf_median": TOL_XF_MEDIAN_DEG,
                              "xf_max": TOL_XF_MAX_DEG, "truth": TOL_TRUTH_DEG,
                              "dev_repro": TOL_DEV_REPRO_DEG},
           "sets": {}}  # fmt: skip
    gate1 = json.loads((HERE.parent / "xf-avg-fix" / "gate1.json").read_text())
    ref = {r["scan"]: r for r in gate1["arms"]["control-m90"]["scans"]}
    for truth in ("control", "held"):
        avg, noavg, cas = (out / f"rang-{truth}-m90", out / f"rang-{truth}-m90_noavg",
                           out / f"casa-{truth}-m90")  # fmt: skip
        if not (avg / "chi.json").exists():
            continue
        ca, cn, cc = _chi(avg), _chi(noavg), _chi(cas)
        xa = _xf(avg / "sim.ms.rang-run" / "calibrate" / "Xf")
        xn = _xf(noavg / "sim.ms.rang-run" / "calibrate" / "Xf")
        xc = _xf(cas / "tables" / "Xf")
        rows = []
        for s in sorted(ca):
            rows.append({"scan": s, "psi_deg": ca[s]["psi_deg"], "chi_avg": ca[s]["chi_deg"],
                         "chi_noavg": cn[s]["chi_deg"], "chi_casa": cc[s]["chi_deg"],
                         "p_avg": ca[s]["p"], "p_casa": cc[s]["p"]})  # fmt: skip
        r = {
            "scans": rows,
            "max_avg_minus_noavg": max(
                abs(x["chi_avg"] - x["chi_noavg"]) for x in rows
            ),
            "max_avg_minus_casa": max(abs(x["chi_avg"] - x["chi_casa"]) for x in rows),
            "max_noavg_minus_casa": max(
                abs(x["chi_noavg"] - x["chi_casa"]) for x in rows
            ),
            "max_avg_minus_33": max(abs(x["chi_avg"] - 33.0) for x in rows),
            "max_noavg_minus_33": max(abs(x["chi_noavg"] - 33.0) for x in rows),
            "max_casa_minus_33": max(abs(x["chi_casa"] - 33.0) for x in rows),
            "xf_avg_vs_noavg_deg": _xf_diff(xa, xn),
            "xf_avg_vs_casa_deg": _xf_diff(xa, xc),
            "xf_noavg_vs_casa_deg": _xf_diff(xn, xc),
        }
        r["G_avg"] = _ok(r["max_avg_minus_noavg"], r["xf_avg_vs_noavg_deg"])
        r["G_casa"] = _ok(r["max_avg_minus_casa"], r["xf_avg_vs_casa_deg"])
        r["G_noavg_casa"] = _ok(r["max_noavg_minus_casa"], r["xf_noavg_vs_casa_deg"])
        r["G_truth"] = bool(r["max_avg_minus_33"] <= TOL_TRUTH_DEG)
        r["G_truth_casa"] = bool(r["max_casa_minus_33"] <= TOL_TRUTH_DEG)
        if truth == "control":
            r["max_dev_repro"] = max(
                abs(x["chi_avg"] - ref[x["scan"]]["chi_fixed_avg"]) for x in rows
            )
            r["G_dev_repro"] = bool(r["max_dev_repro"] <= TOL_DEV_REPRO_DEG)
        res["sets"][truth] = r
    Path(dest).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


def main(argv):
    cmd = argv[0]
    if cmd == "gen":
        gen(argv[1])
    elif cmd == "copydev":
        copydev(argv[1], argv[2])
    elif cmd == "psi":
        psi(argv[1], argv[2], argv[3])
    elif cmd == "rang":
        return rang(argv[1], argv[2], argv[3])
    elif cmd == "casa":
        return casa(argv[1], argv[2])
    elif cmd == "casa_preavg":
        return casa_preavg(argv[1], argv[2], float(argv[3]))
    elif cmd == "posthoc":
        posthoc(argv[1], argv[2])
    elif cmd == "casadefaults":
        return casadefaults(argv[1])
    elif cmd == "score":
        score(argv[1], argv[2])
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
